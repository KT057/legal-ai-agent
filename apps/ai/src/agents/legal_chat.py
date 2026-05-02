"""法務相談チャット用エージェント（RAG 注入 + 1-shot 生成パターン）。

このファイルが扱う AI 概念：

* **RAG injection (1-shot)** — ユーザーの最新発話をクエリに 1 度だけ法令検索し、
  ヒットした条文を system プロンプトの 2 つ目のブロックとして注入してから、
  Claude を 1 回呼んで回答を生成する。
  ReAct 版（``research_agent.py``）と違い、モデル自身は検索しない。
* **Prompt caching (ephemeral)** — 静的な system プロンプトに ``cache_control``
  を付けることで、Anthropic 側でブロック単位に短期キャッシュされる。
  2 回目以降の呼び出しで該当ブロックがヒットすれば入力トークンが値引きされる。
* **2 ブロック system 構成** — 「キャッシュしたい静的部分」と「毎回変わる
  動的な RAG 部分」を別ブロックに分けることで、動的部分が変わってもキャッシュ
  は壊れない。

呼び出し経路: ``routers/legal_chat.py`` (POST /chat) → ``reply()``。
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from ..config import settings
from ..observability import observe, traced_messages_create
from ..rag.formatter import format_citations
from ..rag.retriever import retrieve

# system プロンプトはコードに埋め込まず Markdown ファイルとして外出ししている。
# プロンプトを書き換える際にコード差分にノイズが入らない、レビューしやすい、
# 非エンジニアの法務担当が編集しやすい、といった狙い。
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "legal_chat.md"
LOG = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """1 ターン分の発話。``role`` は user / assistant のどちらか。

    Anthropic Messages API の ``messages`` 配列に渡す要素と 1:1 対応する
    軽量モデル。HTTP 境界での型バリデーションのために pydantic にしている。
    """

    role: Literal["user", "assistant"]
    content: str


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    """system プロンプトの Markdown を 1 度だけ読んでメモリ常駐させる。

    ``lru_cache(maxsize=1)`` は実質「プロセス内シングルトン」で、ファイル I/O を
    リクエスト毎に発生させないための最適化。プロンプトを書き換えたら uvicorn の
    リロードで反映される。
    """
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    """Anthropic 非同期クライアントを 1 つだけ作って使い回す。

    ``AsyncAnthropic`` は内部で HTTP コネクションプールを保持するので、
    リクエスト毎に new するとコネクションを毎回張り直してしまい遅くなる。
    """
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _build_rag_block(query: str) -> str:
    """RAG ブロック（``## 参考法令`` から始まる Markdown）を組み立てる。

    設計判断：

    * RAG が無効、またはクエリが空なら空文字を返す（system に追加しない）
    * 検索が失敗しても **例外を伝播させず** 空文字に縮退する。
      法令 DB が落ちていても「RAG なしの一般論回答」までは返せるよう、
      フォールバック前提で組んでいる。
    """
    if not settings.rag_enabled or not query.strip():
        return ""
    try:
        citations = await retrieve(query, top_k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        # RAG は補助情報なので、Claude 呼び出し本体は止めない。
        LOG.warning("RAG retrieval failed; continuing without citations: %s", exc)
        return ""
    return format_citations(citations)


@observe(name="legal_chat")
async def reply(messages: list[ChatTurn]) -> dict[str, Any]:
    """会話履歴を受け取り、Claude の応答テキストを返す。

    フロー:

    1. 最新 user 発話をクエリに RAG 検索（``_build_rag_block``）。
    2. system を 2 ブロックで構築：
       - [0] 静的プロンプト + ``cache_control: ephemeral``（キャッシュ対象）
       - [1] RAG ブロック（毎回変わるのでキャッシュしない）
    3. Anthropic Messages API を 1 回呼ぶ（tools は使わない＝普通のテキスト生成）。
    4. content 配列から ``type == "text"`` のブロックだけを連結して返す。
    """
    if not messages:
        raise ValueError("messages must not be empty")
    if messages[-1].role != "user":
        # 会話の末尾は必ず user の発話である必要がある（Anthropic API の制約）。
        raise ValueError("last message must be from user")

    # system は単一文字列ではなく「ブロックのリスト」として渡せる。
    # こうすると ``cache_control`` をブロック単位で付けられる。
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt(),
            # ephemeral = 短時間（デフォルト 5 分）の prompt cache 対象。
            # 静的プロンプトをここに置くと、2 回目以降の呼び出しでキャッシュ
            # ヒットすれば該当ブロックぶんの入力トークンが大幅に割引される。
            "cache_control": {"type": "ephemeral"},
        }
    ]
    # 動的ブロック（RAG）は質問ごとに変わるのでキャッシュしない。
    # ここを cache 対象にすると毎回キャッシュミスになって逆効果。
    rag_context = await _build_rag_block(messages[-1].content)
    if rag_context:
        system_blocks.append({"type": "text", "text": rag_context})

    response = await traced_messages_create(
        _client(),
        name="legal_chat.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        # 注: claude-opus-4-7 では temperature パラメータが廃止されているため
        # 渡さない (extended thinking 系モデルはサンプリングが内部で固定される)。
        # 決定論性とハルシネーション抑制はプロンプト側 (prompts/legal_chat.md の
        # 「ハルシネーション防止」節) で担保している。
        system=system_blocks,
        # ChatTurn (pydantic) は API には渡せないので素の dict に戻す。
        messages=[{"role": m.role, "content": m.content} for m in messages],
    )

    # Anthropic のレスポンスは「content block の配列」で返る。
    # text 以外（tool_use 等）が混ざる可能性があるので type で篩う。
    # このエージェントは tools を渡していないので実質 text しか来ないが、
    # 防御的に type フィルタを入れておく。
    text = "".join(b.text for b in response.content if b.type == "text")
    return {"model": response.model, "content": text}
