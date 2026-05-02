"""契約書レビュー用エージェント（強制 tool 呼び出しによる構造化出力）。

このファイルが扱う AI 概念：

* **Tool use as structured output** — JSON を「文字列で出力させてパース」する
  方式は壊れやすい（余計な前置き、コードフェンス、改行混入で失敗する）。
  代わりにツール定義の ``input_schema`` で型を厳密に決め、
  ``tool_choice`` で **そのツールを必ず呼ぶ** ようモデルに強制する。
  すると引数として返ってくる ``block.input`` がスキーマ検証済みの dict になる。
* **Nested JSON Schema** — ``risks: array<object>`` のように入れ子にでき、
  さらに ``severity: enum["low","medium","high"]`` でラベルを縛れる。
  pydantic / TS の Literal とほぼ同じノリで型を細かく書ける。
* **Retrieval query 設計** — 契約全文を埋め込みクエリにすると無関係な条文
  まで雑多に拾うので、タイトル + 本文先頭 800 字を要約代わりに使っている
  （短く・代表的にすることが dense retrieval の精度に直結）。
* **RAG 注入 + tool use の併用** — system に参考法令を注入しつつ、出力は
  ツール経由で構造化する。1 つのリクエストで両方の利点を取る組み合わせ。

呼び出し経路: ``routers/contract_review.py`` (POST /review) → ``review_contract()``。
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from ..config import settings
from ..observability import observe, traced_messages_create
from ..rag.formatter import format_citations
from ..rag.retriever import retrieve

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "contract_review.md"
LOG = logging.getLogger(__name__)

# 構造化出力用ツール。
# このツールは「実行する」ものではなく、**モデルに JSON 構造を吐かせるためだけ**
# に存在する（"ツール" を出力スキーマとして流用する典型パターン）。
# ポイント:
# - input_schema は JSON Schema 準拠
# - severity に enum を置くことで「low/medium/high のいずれか」しか入らない
# - required を絞ることで、欠損のないレポートを保証
# - 配列の items も object として詳細に定義できる
REPORT_TOOL: dict[str, Any] = {
    "name": "report_review",
    "description": "契約書レビュー結果を構造化して返す",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "契約書全体の所感を 2〜4 文で",
            },
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "clause": {
                            "type": "string",
                            "description": "該当する条項名・条番号や引用",
                        },
                        "severity": {
                            "type": "string",
                            # enum で値域を縛ると、UI 側の switch 文が壊れない。
                            "enum": ["low", "medium", "high"],
                        },
                        "reason": {
                            "type": "string",
                            "description": "なぜリスクなのかの説明",
                        },
                        "suggestion": {
                            "type": "string",
                            "description": "具体的な修正提案・代替文言",
                        },
                    },
                    "required": ["clause", "severity", "reason", "suggestion"],
                },
            },
        },
        "required": ["summary", "risks"],
    },
}


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    """契約書レビュー用の system プロンプト Markdown を 1 度だけ読む。"""
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    """Anthropic 非同期クライアントのプロセス内シングルトン。"""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _retrieval_query(title: str, body: str) -> str:
    """契約タイトル + 本文先頭 800 字を retrieval クエリにする。

    契約全文（数千〜数万字）をそのまま埋め込みクエリに使うと、
    - 埋め込み API のコストが上がる
    - ベクトルが「契約書一般の何か」に平均化されて精度が落ちる
    という二重苦になる。タイトル + 冒頭 800 字に絞るのは、
    「見出し + 第一目的条項」がドキュメントの代表ベクトルとして妥当、という経験則。
    """
    head = body[:800]
    return f"{title}\n{head}"


async def _build_rag_block(title: str, body: str) -> str:
    """RAG ブロック（``## 参考法令``）を組み立てる。失敗時は空文字に縮退。

    ``legal_chat._build_rag_block`` と同じ縮退戦略：retrieval が落ちても
    レビュー本体は止めない（参考法令なしでもレビューは出せるから）。
    """
    if not settings.rag_enabled:
        return ""
    try:
        citations = await retrieve(_retrieval_query(title, body), top_k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("RAG retrieval failed; continuing without citations: %s", exc)
        return ""
    return format_citations(citations)


@observe(name="contract_review")
async def review_contract(title: str, body: str) -> dict[str, Any]:
    """契約書を Claude にレビューさせ、構造化レポートを返す。

    フロー:

    1. RAG で参考法令を取得（縮退あり）
    2. system を 2 ブロック（静的プロンプト + RAG）で構築
    3. ``tools=[REPORT_TOOL]`` + ``tool_choice={"type":"tool","name":"report_review"}``
       で **必ず** report_review ツールを呼ばせる
    4. レスポンスから tool_use ブロックを取り出し ``block.input`` を返却

    なぜ ``tool_choice`` を明示するか：
    - 既定の ``"auto"`` だと、自由テキストで答えてしまうケースが残る
    - ``{"type": "tool", "name": ...}`` を指定すると「テキストで答える」自由を奪える
    - これによりエンドポイント側のレスポンス型を保証できる
    """
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt(),
            # 静的プロンプトはキャッシュ対象。RAG は別ブロックで cache_control なし。
            "cache_control": {"type": "ephemeral"},
        }
    ]
    rag_context = await _build_rag_block(title, body)
    if rag_context:
        system_blocks.append({"type": "text", "text": rag_context})

    response = await traced_messages_create(
        _client(),
        name="contract_review.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        # 注: claude-opus-4-7 では temperature パラメータが廃止されているため
        # 渡さない。ハルシネーション抑制はプロンプト側 (prompts/contract_review.md
        # の「ハルシネーション防止」節) と tool_choice による構造化強制で担保。
        system=system_blocks,
        tools=[REPORT_TOOL],
        # 「自由回答禁止、必ずこのツールを呼べ」をモデルに強制。
        # この行を消して "auto" にすると、稀に tool_use 無しでテキストだけ返ってきて
        # 後段の RuntimeError に落ちる。
        tool_choice={"type": "tool", "name": "report_review"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"# 契約書タイトル\n{title}\n\n"
                    # コードフェンスで囲むのは「ここからここまでが契約本文」を
                    # モデルに明示するための簡易デリミタ。本文中に Markdown 記法が
                    # 混じっていても system 側の指示と混線しにくくなる。
                    f"# 契約書本文\n```\n{body}\n```\n\n"
                    "上記契約書をレビューし、`report_review` ツールで結果を返してください。"
                ),
            }
        ],
    )

    # 強制 tool_choice を付けてもレスポンスは content[] 形式で返るので、
    # 該当する tool_use ブロックを 1 つ探して payload を取り出す。
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_review":
            # block.input は input_schema に従ってバリデーション済みの dict。
            # （SDK のバージョンによっては Pydantic オブジェクトの場合もあるので isinstance で防御）
            payload = block.input
            if isinstance(payload, dict):
                return {
                    "model": response.model,
                    "summary": payload.get("summary", ""),
                    "risks": payload.get("risks", []),
                }

    # tool_choice で強制している以上、ここに来たらほぼ Anthropic 側の仕様変更か
    # max_tokens 不足で出力が途中で切れた疑い。呼び出し側で 502 にして良い状態。
    raise RuntimeError("Claude did not return a tool_use block for report_review")
