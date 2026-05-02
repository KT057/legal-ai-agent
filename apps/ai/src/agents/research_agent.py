"""ReAct スタイルの法務リサーチエージェント。

このファイルが扱う AI 概念：

* **ReAct (Reason + Act) loop** — モデル自身が「いつ・何を・何回検索するか」
  を決める。1 ターンの中で：
  1. モデルが ``tool_use`` ブロックを返す（= 検索したい）
  2. 我々がローカルでツールを実行
  3. ``tool_result`` を user メッセージに入れて返す
  4. モデルがそれを観察してまた行動を決める…を繰り返す
* **Agentic retrieval vs RAG injection** — ``legal_chat.py`` は「事前に 1 回
  検索 → 結果を system に注入 → 1 回生成」の固定パイプライン。
  本ファイルは「モデルが必要なだけ反復検索する」設計で、初期クエリが弱くても
  リカバリできる代わりにレイテンシ・トークンコストが高い。
* **Tool schema (JSON Schema)** — ``input_schema`` は API 側で型検証される。
  ``required`` を絞って ``properties`` を厳しく書くほど、モデルが構造化された
  入力を出してくる確率が上がる。
* **Content block の dict 化** — Anthropic SDK は「型付きオブジェクト」を返す
  が、それをもう一度 messages に積む時には素の dict に戻さないと API が
  受け取れない（``_block_to_dict`` 参照）。
* **暴走対策** — ``max_iterations`` を必ず設定する。モデルが永久に検索し続けて
  トークンと時間を食い潰すのを防ぐ最低限のガードレール。

呼び出し経路: ``routers/research.py`` (POST /research) → ``research()``。
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropic

from ..config import settings
from ..observability import observe, traced_messages_create
from ..rag.retriever import Citation, retrieve

LOG = logging.getLogger(__name__)

# ReAct 用の system プロンプト。
# - ツールの存在を明示し、いつ呼ぶべきかを誘導
# - 引用 ID 形式 [citation_id] を強制（後段の評価でも使う）
# - 最終回答のフォーマット（結論 → 根拠 → 注意）を統一
SYSTEM_PROMPT = (
    "あなたは日本の法務リサーチを担当する AI アシスタントです。"
    "ユーザーの質問に答えるにあたって、必要に応じて `search_laws` ツールで"
    "法令データベースを検索し、関連条文を集めてから回答してください。"
    "1 回の検索で十分でない場合は、観点を変えて複数回検索しても構いません。"
    "得られた条文を引用する際は、引用末尾に必ず `[citation_id]` を付与してください。"
    "最終回答は日本語で、結論 → 根拠条文 → 注意事項 の順に簡潔にまとめます。"
    "最終判断は弁護士・所轄官庁に確認するよう必ず添えてください。"
    "\n\n## ハルシネーション防止 (絶対遵守)"
    "\n- `search_laws` の結果に存在しない法令名・条番号・項番を、具体的な数字付きで挙げてはならない"
    "(未取得の条文の作出は禁止)。"
    "\n- 判例名・通達名・ガイドライン名は、検索結果に出てこないものを挙げない。"
    "\n- 検索しても該当条文が見つからなかった場合は、その旨を率直に伝え、推測で答えてはいけない。"
    "\n- 確信が持てない事実は「確認が必要」と明示する。"
    "「〜だったと思います」のような曖昧な断定は禁止。"
    "\n- 一般論しか言えない場合は「一般論として」と前置きし、具体的な条番号は出さない。"
)

# Claude に渡すツール定義。
# input_schema は **JSON Schema** (Draft 2020-12 ベース)。
# - properties で各引数の型・説明を書く
# - required で必須引数を列挙（ここに無いものは省略可能）
# - default は API バリデーションには使われないので、フォールバックは
#   ``_execute_search_laws`` 側で settings.rag_top_k を使って自前で対応する
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_laws",
        "description": (
            "法令データベース (e-Gov 由来 / pgvector + Voyage 埋め込み) に対して"
            "意味検索を行い、関連条文の上位 K 件を返す。"
            "質問と直接対応する条文を探したい時、または前段の検索結果が"
            "不十分な時に呼ぶ。検索クエリは具体的にすること。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ。日本語で具体的に。",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返す件数 (1〜10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
]


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    """Anthropic 非同期クライアントのプロセス内シングルトン。HTTP 接続を使い回す。"""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _format_search_result(citations: list[Citation], offset: int) -> str:
    """検索結果をモデルが読みやすい **テキスト** に整形する。

    モデルに渡す ``tool_result`` の content は文字列でも構造体でもよいが、
    ここでは可読性重視でプレーンテキストに寄せている。
    重要なのは ``[citation_id=N]`` を埋め込むこと：
    最終回答で同じ ID を再利用させるための「引用整合の手がかり」になる。

    Parameters
    ----------
    citations:
        retriever が返した ``Citation`` のリスト。
    offset:
        既に直前までの検索で見たことになっている件数 + 1。
        反復検索で ID が衝突しないよう、検索ラウンドをまたいでオフセットする。
    """
    if not citations:
        return "(該当する条文は見つかりませんでした)"
    lines: list[str] = []
    for idx, c in enumerate(citations, start=offset):
        article = c.article_no or ""
        if c.article_title:
            article = f"{article}（{c.article_title}）" if article else f"（{c.article_title}）"
        lines.append(f"[citation_id={idx}] {c.law_title}（{c.law_num}）{article}".rstrip())
        lines.append(f"score={c.score:.3f}")
        body = c.body.strip()
        # 条文本文が極端に長い場合、コンテキスト圧迫とコスト増を避けるため
        # 600 字で打ち切る（実運用ではこの長さでも法令条文として成立しやすい）。
        if len(body) > 600:
            body = body[:600] + "…(truncated)"
        lines.append(body)
        lines.append(f"出典: {c.source_url}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def _execute_search_laws(
    tool_input: dict[str, Any],
    citations_seen: list[Citation],
) -> str:
    """``search_laws`` ツール本体。引数を検証して RAG retriever に流す。

    モデルが渡してくる ``tool_input`` は JSON Schema で検証されているとはいえ、
    ``int`` フィールドに文字列が来る等の境界ケースに備えて型を再キャスト
    する。空クエリ等の異常時はエラー文字列を返し、モデルに「失敗した」事実を
    観察させてリトライさせる（例外を上げると ReAct ループが落ちてしまう）。
    """
    query = str(tool_input.get("query", "")).strip()
    top_k = int(tool_input.get("top_k", settings.rag_top_k))
    # モデルがでたらめに大きい K を要求してきた時のクランプ。
    top_k = max(1, min(10, top_k))
    if not query:
        return "(error: query is empty)"
    try:
        results = await retrieve(query, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("search_laws failed: %s", exc)
        return f"(error: retrieval failed: {exc})"
    # citation_id をラウンドをまたいで重複しないよう連番で振る。
    offset = len(citations_seen) + 1
    citations_seen.extend(results)
    return _format_search_result(results, offset)


@observe(name="research_agent")
async def research(question: str, max_iterations: int = 5) -> dict[str, Any]:
    """ReAct ループを回し、モデルがツールを呼ばなくなった時点を最終回答とする。

    1 イテレーションの内訳:

    1. ``messages.create(tools=TOOLS, ...)`` を呼ぶ
    2. レスポンスから ``tool_use`` ブロックを抽出
    3. 無ければ → text を集めて return（= 最終回答）
    4. あれば →
       a. assistant のメッセージとして response.content を **そのまま** 蓄積
          （後続のツール結果を受けるためにモデルの「考え」を残す必要がある）
       b. 各 tool_use をローカル実行
       c. ``tool_result`` ブロックを並べて user メッセージとして追加
    5. ``iterations += 1`` して再ループ

    ``max_iterations`` 到達時はモデルが収束していない（探索が発散した）と判断し、
    切断メッセージを返す。
    """
    if not question.strip():
        raise ValueError("question must not be empty")

    # 初手は user の質問のみ。messages はループのたびに伸びていく。
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    citations_seen: list[Citation] = []
    started = time.perf_counter()
    # トークン会計：プロンプトキャッシュのヒット率や 1 質問あたりのコスト試算に使う。
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0
    last_model = ""

    while iterations < max_iterations:
        # 各イテレーションで API を 1 回叩く。tools を渡しているので、
        # モデルは「ツールを呼ぶ」「テキストで答える」の両方を選べる状態。
        response = await traced_messages_create(
            _client(),
            name=f"research_agent.iteration[{iterations}]",
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            # 注: claude-opus-4-7 では temperature パラメータが廃止されているため
            # 渡さない。ReAct のクエリ揺らぎとハルシネーションは SYSTEM_PROMPT の
            # 「ハルシネーション防止」節で担保 (検索結果に無い条文の作出を禁止)。
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # system は固定なのでキャッシュ対象。messages 側は毎回伸びるが、
                    # Anthropic はプレフィックス一致でキャッシュを利かせるため、
                    # 同じ system を使い続ける限りキャッシュは効き続ける。
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOLS,
            messages=messages,
        )
        last_model = response.model
        # usage は SDK のバージョンによって型が違うことがあるので getattr で防御的に。
        usage = getattr(response, "usage", None)
        if usage is not None:
            total_input_tokens += getattr(usage, "input_tokens", 0) or 0
            total_output_tokens += getattr(usage, "output_tokens", 0) or 0

        # 「モデルがツールを呼んだか？」が ReAct ループの分岐点。
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            # ツールを呼ばなかった = モデルは答えを出したと判断。最終回答を抽出して終了。
            text = "".join(b.text for b in response.content if b.type == "text")
            return {
                "model": last_model,
                "content": text,
                "iterations": iterations,
                "citations": [asdict(c) for c in citations_seen],
                "usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        # モデルの返答全体（text + tool_use 混在）を assistant ターンとして
        # メッセージ履歴に積む。ここで取りこぼすと、続く tool_result が
        # 「どの tool_use への返答か」を API がトラッキングできずエラーになる。
        # SDK の型付きオブジェクトのままでは API に再送できないので dict に戻す。
        messages.append(
            {
                "role": "assistant",
                "content": [_block_to_dict(b) for b in response.content],
            }
        )
        # 全 tool_use をローカル実行し、結果を tool_result ブロック配列にまとめる。
        # 1 ターンに複数ツールを並列で呼んでくることがあるため、リストで対応。
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            if tu.name == "search_laws":
                tool_input = tu.input if isinstance(tu.input, dict) else {}
                result_text = await _execute_search_laws(tool_input, citations_seen)
            else:
                # 知らないツール名が来た場合：例外で落とすのではなく
                # エラー文字列をモデルに観察させて自己修正のチャンスを与える。
                result_text = f"(error: unknown tool: {tu.name})"
            tool_results.append(
                {
                    "type": "tool_result",
                    # tool_use_id でどの tool_use への結果かをひも付ける（必須）。
                    "tool_use_id": tu.id,
                    "content": result_text,
                }
            )
        # tool_result は user ターンの content として渡すのが Anthropic の規約。
        messages.append({"role": "user", "content": tool_results})
        iterations += 1

    # ループ脱出 = max_iterations に到達。発散したか、ツール濫用が起きている可能性。
    # 完全な回答は返せないが、収集済みの citations は呼び出し側に渡す。
    return {
        "model": last_model,
        "content": ("(max_iterations に到達しました。検索を絞り込めなかった可能性があります。)"),
        "iterations": iterations,
        "citations": [asdict(c) for c in citations_seen],
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def _block_to_dict(block: Any) -> dict[str, Any]:
    """SDK の content block オブジェクトを「再送可能な dict」に変換する。

    Anthropic SDK は ``response.content`` を Pydantic ライクな型付きオブジェクトで
    返してくる（例: ``TextBlock(type='text', text='...')``）。これをそのまま
    ``messages.create(messages=[{"role": "assistant", "content": [...]}])`` に
    入れると API 側で形式エラーになる。属性を取り出してプレーン dict に戻すのが
    ReAct ループでは必須の前処理。

    text / tool_use 以外のブロック（thinking 等の将来拡張）は最低限 type だけ
    保持して落とす方針にしている（フィールドを失っても再送して動く確率が高い）。
    """
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": block.type}
