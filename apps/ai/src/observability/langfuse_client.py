"""Langfuse SDK のシングルトン管理 + Anthropic 呼び出しの計装ヘルパー。

このファイルが扱う AI 概念：

* **trace / span / generation** — Langfuse の観測単位の階層。
  - trace: ユーザリクエスト 1 件 = 1 ルート (例: ``legal_chat`` 全体)
  - span: trace の子要素 (例: ``rag.retrieve``、検索処理など LLM 以外)
  - generation: LLM 呼び出し 1 回 (input/output/usage/model を持つ特殊な span)
* **prompt cache の可視化** — Anthropic レスポンスの ``cache_creation_input_tokens``
  / ``cache_read_input_tokens`` を ``usage_details`` に渡すと、Langfuse 上で
  キャッシュヒット率と節約トークン量が時系列で見える。
* **フィーチャーフラグでの計装 on/off** — ``LANGFUSE_TRACING_ENABLED=false`` で
  全計装が no-op になる。Langfuse が落ちていても本体は動く設計。

呼び出し経路: agents / rag / evals から ``@observe`` と ``traced_messages_create``
を import して使う。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from anthropic import AsyncAnthropic

from ..config import settings

LOG = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ``langfuse.decorators`` のグローバルクライアントは ``os.environ`` を直読みする。
# pydantic-settings 経由で読んだ ``.env`` の値はここに反映されないため、
# モジュール初回 import 時にブリッジしておく。これにより agent / RAG / evals 側の
# ``@observe`` で発行される暗黙クライアントも正しく初期化される。
if (
    settings.langfuse_tracing_enabled
    and settings.langfuse_public_key
    and settings.langfuse_secret_key
):
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)


def tracing_enabled() -> bool:
    """Langfuse へ送信するかどうかの判定。

    フラグが立っていても、キーが片方でも空なら no-op に倒す
    (``.env.example`` をそのまま使った状態で誤送信が起きないようにするため)。
    """
    return bool(
        settings.langfuse_tracing_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    )


@lru_cache(maxsize=1)
def get_langfuse() -> Any | None:
    """Langfuse クライアントのプロセス内シングルトン。無効化時は ``None``。

    ``langfuse`` パッケージが import できない／キーが無いときも例外を投げず
    ``None`` を返す。呼び出し側は ``if client is None: return`` の防御を書く必要があるが、
    その分計装の有無で挙動が分岐しないので運用上の事故が減る。
    """
    if not tracing_enabled():
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        LOG.warning("langfuse package is not installed; tracing disabled")
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("failed to init Langfuse client; tracing disabled: %s", exc)
        return None


def flush_langfuse() -> None:
    """送信キューを即時フラッシュする。

    Langfuse はバックグラウンドスレッドで送信するため、プロセス終了直前に
    呼んでおかないと最後のリクエストの trace が落ちる。FastAPI の lifespan
    shutdown と evals の main の終端で呼ぶ。
    """
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("langfuse flush failed: %s", exc)


def observe(*dargs: Any, **dkwargs: Any) -> Any:
    """``langfuse.decorators.observe`` の薄いラッパー。

    無効化時は何もしない identity decorator を返す。これにより、
    呼び出し側は ``@observe()`` を貼っておくだけで、設定で完全に外せる。

    呼び出し方は本家と同じ：

    >>> @observe()
    ... async def reply(...): ...

    >>> @observe(name="rag.retrieve")
    ... async def retrieve(...): ...
    """
    if not tracing_enabled():

        def _identity(fn: F) -> F:
            return fn

        # ``@observe`` (括弧なし) で関数を直接渡されたケースに対応
        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            return dargs[0]
        return _identity

    try:
        from langfuse.decorators import observe as _lf_observe  # type: ignore[import-not-found]
    except ImportError:
        LOG.warning("langfuse.decorators not available; observe is no-op")

        def _identity2(fn: F) -> F:
            return fn

        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            return dargs[0]
        return _identity2

    return _lf_observe(*dargs, **dkwargs)


def _summarize_response(response: Any) -> str | list[dict[str, Any]]:
    """Anthropic レスポンスを Langfuse の output として記録できる形に整形。

    text のみなら文字列、tool_use 等が混じるなら最低限の dict 配列にして、
    UI 上で何が返ったかが追えるようにする。
    """
    blocks = getattr(response, "content", []) or []
    text_parts = [getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"]
    if all(getattr(b, "type", None) == "text" for b in blocks):
        return "".join(text_parts)
    summary: list[dict[str, Any]] = []
    for b in blocks:
        btype = getattr(b, "type", "")
        if btype == "text":
            summary.append({"type": "text", "text": getattr(b, "text", "")})
        elif btype == "tool_use":
            summary.append(
                {
                    "type": "tool_use",
                    "name": getattr(b, "name", ""),
                    "input": getattr(b, "input", None),
                }
            )
        else:
            summary.append({"type": btype})
    return summary


def _usage_details(response: Any) -> dict[str, int]:
    """Anthropic ``usage`` から Langfuse の ``usage_details`` 形式に変換。

    cache_creation_input_tokens / cache_read_input_tokens を別キーで残すことで、
    Langfuse UI の Generations タブで ``input + cache_creation + cache_read`` の
    内訳がスタックグラフとして見える。
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
        "cache_creation_input": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


async def traced_messages_create(
    client: AsyncAnthropic,
    *,
    name: str,
    **kwargs: Any,
) -> Any:
    """``client.messages.create(**kwargs)`` を Langfuse の generation として記録する。

    無効化時は素通しで Anthropic API を叩くだけ (オーバーヘッドゼロ)。
    有効時は parent trace の下に generation observation を 1 つ作り、
    input / output / model / usage_details / metadata を詰める。

    呼び出し側は ``await _client().messages.create(**kwargs)`` を
    ``await traced_messages_create(_client(), name="...", **kwargs)`` に
    置き換えるだけで済む。
    """
    if not tracing_enabled():
        return await client.messages.create(**kwargs)
    # ``_traced_call`` 側で ``@observe(as_type="generation")`` が generation
    # observation を作る。親 trace が無くても Langfuse SDK が暗黙に root を発行する
    # ので、agent 関数に @observe を貼り忘れていても落ちない（が、見栄えは悪くなる）。
    return await _traced_call(client, name=name, **kwargs)


# ``@observe(as_type="generation")`` は import 時にしか張れない。
# tracing_enabled() が False のときは ``observe`` が identity を返すため、
# 結果として _traced_call は素のコルーチンになる (= no-op)。
@observe(as_type="generation")
async def _traced_call(client: AsyncAnthropic, *, name: str, **kwargs: Any) -> Any:
    """generation observation の中身。tracing 無効時は @observe が外れて素通し。"""
    try:
        from langfuse.decorators import langfuse_context  # type: ignore[import-not-found]

        langfuse_context.update_current_observation(
            name=name,
            model=kwargs.get("model"),
            input=kwargs.get("messages"),
            metadata={
                "system": _system_summary(kwargs.get("system")),
                "max_tokens": kwargs.get("max_tokens"),
                "tools": [t.get("name") for t in kwargs.get("tools", []) or []],
                "tool_choice": kwargs.get("tool_choice"),
            },
        )
    except ImportError:
        pass

    response = await client.messages.create(**kwargs)

    try:
        from langfuse.decorators import langfuse_context  # type: ignore[import-not-found]

        langfuse_context.update_current_observation(
            output=_summarize_response(response),
            model=getattr(response, "model", kwargs.get("model")),
            usage_details=_usage_details(response),
        )
    except ImportError:
        pass
    return response


def _system_summary(system: Any) -> Any:
    """``system`` ブロックを Langfuse metadata 用に圧縮表現する。

    プロンプト全文を毎 trace に流すと観測 DB がすぐ膨らむため、
    blocks の type と長さだけ残す。プロンプト本文は Langfuse Prompts 機能で
    別管理する想定。
    """
    if system is None:
        return None
    if isinstance(system, str):
        return {"type": "string", "length": len(system)}
    if isinstance(system, list):
        return [
            {
                "type": b.get("type"),
                "length": len(b.get("text", "")) if isinstance(b, dict) else 0,
                "cached": isinstance(b, dict) and bool(b.get("cache_control")),
            }
            for b in system
        ]
    return {"type": type(system).__name__}
