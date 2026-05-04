"""NDA ドラフト生成用のワークフロー型エージェント。

このファイルが扱う AI 概念：

* **Multi-phase agentic workflow** — 1 つの「契約ドラフトを作る」タスクを、
  4 つの phase (hearing → draft → review → revise) に分け、それぞれで Claude を
  違う設定で呼び分ける。phase ごとに system プロンプトとツール構成が変わる。
* **Tool-driven hearing** — ヒアリングフェーズはモデルに自由テキストで
  返答させず、`update_requirements` / `ask_user` のどちらかを必ず呼ばせる
  (`tool_choice="any"`)。これにより「現時点で確定した要件」を構造化された
  状態で取り出せ、フロントの UI に直接バインドできる。
* **Self-review pattern** — 同じ AI が同じドラフトを別 phase で読み返し、
  ``contract_review`` 風の構造化リスク評価に通す。検出されたリスクを次の
  revise phase の system に注入し、自己改善ループを 1 往復回す。
* **Phase 別 system プロンプト** — phase 切り替えのたびに system が変わるので、
  キャッシュは phase 単位で別 key になる。代わりに phase 内では同じ静的
  プロンプトが使われ続けるのでキャッシュが効く。

呼び出し経路：

* ``routers/contract_draft.py`` (POST /draft/hearing) → ``hearing_turn()``
* ``routers/contract_draft.py`` (POST /draft/generate) → ``generate_full_draft()``
* eval ハーネス → ``generate_from_requirements()`` (hearing スキップで一発生成)
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..config import settings
from ..observability import observe, traced_messages_create
from ..rag.formatter import format_citations
from ..rag.retriever import retrieve

LOG = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 必須 6 項目すべてが埋まったら hearing 終了とみなす。
_REQUIRED_FIELDS: tuple[str, ...] = (
    "disclosing_party",
    "receiving_party",
    "purpose",
    "confidential_info_scope",
    "term_months",
    "governing_law",
)

# Claude が ask_user を呼び忘れた時のフォールバック質問用 (ユーザーには英語フィールド名を見せない)。
_FIELD_LABELS_JA: dict[str, str] = {
    "disclosing_party": "開示者 (秘密情報を渡す側) の正式社名",
    "receiving_party": "受領者 (秘密情報を受け取る側) の正式社名",
    "purpose": "秘密情報を開示する目的",
    "confidential_info_scope": "秘密情報として保護する対象の範囲",
    "term_months": "契約有効期間 (月単位)",
    "governing_law": "準拠法",
}


class RequirementsDraft(BaseModel):
    """NDA ドラフトに必要な要件の「現状埋まっている分」。

    * Python 内部は snake_case 属性 (PEP 8)、JSON 入出力は camelCase キー
      (TypeScript 側の ``RequirementsDraft`` と直接互換) になるよう
      ``alias_generator=to_camel`` + ``populate_by_name=True`` を設定。
    * 全フィールド optional。hearing が進むにつれて埋まっていき、
      ``is_complete()`` が True になった時点で generate phase に進める。
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # extra フィールドは破棄 (古いクライアントが未知のキーを送ってきても落ちない)。
        extra="ignore",
    )

    disclosing_party: str | None = Field(default=None)
    receiving_party: str | None = Field(default=None)
    purpose: str | None = Field(default=None)
    confidential_info_scope: str | None = Field(default=None)
    term_months: int | None = Field(default=None)
    governing_law: str | None = Field(default=None)

    def is_complete(self) -> bool:
        """必須 6 項目がすべて非空か。これが True なら hearing を終わらせて良い。"""
        return all(_truthy(getattr(self, name)) for name in _REQUIRED_FIELDS)

    def merge(self, other: RequirementsDraft) -> RequirementsDraft:
        """``other`` の非空フィールドだけを self に上書きした新インスタンスを返す。

        モデルが毎ターン「現状全体」を返してくる前提だが、稀に既存値を空で
        塗り潰してくるケースがあるので、防御的に「空でない値だけ採用」する。
        """
        merged = self.model_dump()
        for name in _REQUIRED_FIELDS:
            new_val = getattr(other, name)
            if _truthy(new_val):
                merged[name] = new_val
        return RequirementsDraft(**merged)


def _truthy(value: Any) -> bool:
    """None / 空文字 / 0 を「未入力」、それ以外を「入力済み」と扱う。

    ``term_months`` は 0 だと有効期間が無くなるので、これも未入力扱いにしてよい。
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int):
        return value > 0
    return True


# ヒアリングフェーズで使う 2 つのツール。
#
# どちらを呼ぶかはモデルに任せる (``tool_choice="any"``)。
# - update_requirements: 「現時点で判明している要件すべて」を一括で送る
# - ask_user: 不足項目について次の質問を出す
#
# 1 ターンで両方呼ぶこともある (要件を更新しつつ次の質問もする) ことを許容する。
HEARING_TOOLS: list[dict[str, Any]] = [
    {
        "name": "update_requirements",
        "description": (
            "現時点で確定した NDA の要件をすべて (差分ではなく現状全体を) 渡す。"
            "ユーザーから新たな情報が得られたら、既存の確定済み項目と合わせて毎回呼ぶ。"
            "値が分からない項目は省略すること (空文字や仮の値を入れない)。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "disclosingParty": {
                    "type": "string",
                    "description": "開示者 (秘密情報を渡す側) の正式社名",
                },
                "receivingParty": {
                    "type": "string",
                    "description": "受領者 (秘密情報を受け取る側) の正式社名",
                },
                "purpose": {
                    "type": "string",
                    "description": "秘密情報を開示する目的 (例: 製品の共同検証)",
                },
                "confidentialInfoScope": {
                    "type": "string",
                    "description": "秘密情報として保護する対象 (例: 技術情報、顧客情報)",
                },
                "termMonths": {
                    "type": "integer",
                    "description": "契約有効期間。月単位の整数。年単位で言われたら × 12 する",
                    "minimum": 1,
                    "maximum": 600,
                },
                "governingLaw": {
                    "type": "string",
                    "description": "準拠法。日本企業同士なら通常「日本法」",
                },
            },
            # required は付けない: 部分的に判明した時点で呼べるようにするため。
        },
    },
    {
        "name": "ask_user",
        "description": (
            "不足している要件をユーザーに 1 つだけ尋ねる。"
            "1 ターン 1 項目を原則とする (複数項目を 1 文に詰め込まない)。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "ユーザーへの質問文 (日本語、敬体)",
                },
                "missingField": {
                    "type": "string",
                    "description": "この質問で埋めたい項目の camelCase キー",
                    "enum": [
                        "disclosingParty",
                        "receivingParty",
                        "purpose",
                        "confidentialInfoScope",
                        "termMonths",
                        "governingLaw",
                    ],
                },
            },
            "required": ["question", "missingField"],
        },
    },
]

# review phase 用の構造化出力ツール。``contract_review.py`` の REPORT_TOOL と
# 同じ形式 (UI 側の表示コードを共通化できるため意図的に揃えている)。
REPORT_TOOL: dict[str, Any] = {
    "name": "report_review",
    "description": "NDA ドラフトのリスクを構造化して返す",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "ドラフト全体の所感を 2〜4 文で",
            },
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "clause": {
                            "type": "string",
                            "description": "該当する条項見出し (例: 第3条 (秘密情報の範囲))",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "reason": {
                            "type": "string",
                            "description": "なぜリスクなのかの説明",
                        },
                        "suggestion": {
                            "type": "string",
                            "description": "具体的な修正方針・代替文言",
                        },
                    },
                    "required": ["clause", "severity", "reason", "suggestion"],
                },
            },
        },
        "required": ["summary", "risks"],
    },
}


PhaseLiteral = Literal["hearing", "generate", "review", "revise"]


@lru_cache(maxsize=4)
def _system_prompt(phase: PhaseLiteral) -> str:
    """phase 別の system プロンプト Markdown を 1 度だけ読んでメモリ常駐。

    ``lru_cache(maxsize=4)`` は phase 数 (4) と一致。phase 切り替えごとに
    別の system が読まれ、内部で別キャッシュエントリになる。
    """
    return (PROMPTS_DIR / f"contract_draft_{phase}.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    """Anthropic 非同期クライアントのプロセス内シングルトン。"""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _build_rag_block(query: str) -> str:
    """RAG ブロック (``## 参考法令``) を組み立てる。失敗時は空文字に縮退。

    既存 ``legal_chat`` / ``contract_review`` と同じフォールバック戦略：
    retrieval が落ちても本体ロジックは止めない。
    """
    if not settings.rag_enabled or not query.strip():
        return ""
    try:
        citations = await retrieve(query, top_k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("RAG retrieval failed; continuing without citations: %s", exc)
        return ""
    return format_citations(citations)


def _block_to_dict(block: Any) -> dict[str, Any]:
    """SDK の content block オブジェクトを「再送可能な dict」に戻す。

    ``research_agent._block_to_dict`` と同じ振る舞い。tool_use の連鎖を
    messages 配列に積み直すために必要。
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


# ─────────────────────────────────────────────────────────────
# Hearing phase
# ─────────────────────────────────────────────────────────────


class HearingTurnInput(BaseModel):
    """``hearing_turn()`` の入力。1 ターン分のメッセージ + 既知の要件。"""

    history: list[dict[str, str]] = Field(default_factory=list)
    user_message: str
    current_requirements: RequirementsDraft = Field(default_factory=RequirementsDraft)


class HearingTurnResult(BaseModel):
    """``hearing_turn()`` の出力。Assistant の発話と更新後の要件。"""

    model: str
    assistant_message: str
    requirements: RequirementsDraft
    is_complete: bool
    pending_question: str | None = None
    missing_field: str | None = None


@observe(name="contract_draft.hearing")
async def hearing_turn(payload: HearingTurnInput) -> HearingTurnResult:
    """ヒアリングを 1 ターン進める。

    フロー:

    1. system に hearing 用プロンプト + 「現在埋まっている要件」を 2 ブロック構成で渡す
    2. tools=[update_requirements, ask_user] / ``tool_choice="any"`` で必ずどちらかを呼ばせる
    3. レスポンスから tool_use を 0〜2 件取り出し:
       - update_requirements の input を既知要件にマージ
       - ask_user の question を「assistant の発話」として返す
    4. 全項目が埋まれば ``is_complete=True`` を返し、フロントは generate ボタンを活性化
    """
    if not payload.user_message.strip():
        raise ValueError("user_message must not be empty")

    # 動的ブロック: 「現時点で埋まっている要件」を JSON で見せると、モデルが
    # 「次に何を聞くべきか」を判断しやすい。
    current_block = (
        "## 現在の要件 (camelCase)\n"
        "```json\n"
        f"{payload.current_requirements.model_dump_json(by_alias=True, indent=2)}\n"
        "```"
    )

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("hearing"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": current_block},
    ]

    messages: list[dict[str, Any]] = []
    for h in payload.history:
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": payload.user_message})

    response = await traced_messages_create(
        _client(),
        name="contract_draft.hearing.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        tools=HEARING_TOOLS,
        # ``"any"`` = tools のうちいずれかを必ず呼ぶ。自由テキストで返す自由を奪うことで、
        # 構造化された要件抽出と質問テキストを必ず取り出せる。
        tool_choice={"type": "any"},
        messages=messages,
    )

    updated = payload.current_requirements
    pending_question: str | None = None
    missing_field: str | None = None

    for block in response.content:
        if block.type != "tool_use":
            continue
        if block.name == "update_requirements":
            tool_input = block.input if isinstance(block.input, dict) else {}
            try:
                # camelCase キーで来るので alias 経由で読み込む。
                # populate_by_name=True により snake_case でも読める。
                incoming = RequirementsDraft.model_validate(tool_input)
            except Exception as exc:  # noqa: BLE001
                # モデルが壊れた値を入れてきた時のフォールバック (例: termMonths が文字列)。
                # 警告ログだけ残してそのターンの更新はスキップ。次ターンでリトライさせる。
                LOG.warning("update_requirements payload invalid: %s", exc)
                continue
            updated = updated.merge(incoming)
        elif block.name == "ask_user":
            tool_input = block.input if isinstance(block.input, dict) else {}
            pending_question = str(tool_input.get("question", "")).strip() or None
            missing_field = str(tool_input.get("missingField", "")).strip() or None

    # 完了判定: 全項目が埋まったら is_complete=True を返す。
    # この場合 ask_user が呼ばれていなくても良い (むしろ呼ばれない方が自然)。
    completed = updated.is_complete()

    if completed:
        assistant_message = (
            "必要な要件はすべて確認できました。"
            "右側の「ドラフトを生成」ボタンを押すと、最初のドラフトが生成されます。"
        )
    elif pending_question:
        assistant_message = pending_question
    else:
        # update_requirements は呼ばれたが ask_user が呼ばれなかった (= 揃っていないのに質問なし)。
        # 安全策として「次の不足項目」を 1 つ示して再質問させる。
        next_missing = next(
            (name for name in _REQUIRED_FIELDS if not _truthy(getattr(updated, name))),
            None,
        )
        assistant_message = (
            f"続けて、{_FIELD_LABELS_JA.get(next_missing, next_missing)}について教えてください。"
            if next_missing
            else "もう少し詳しく教えてください。"
        )

    return HearingTurnResult(
        model=response.model,
        assistant_message=assistant_message,
        requirements=updated,
        is_complete=completed,
        pending_question=pending_question,
        missing_field=missing_field,
    )


# ─────────────────────────────────────────────────────────────
# Generate (draft → review → revise) phase
# ─────────────────────────────────────────────────────────────


class GenerateResult(BaseModel):
    """``generate_full_draft()`` の出力。3 phase 分の成果物 + 計装メタ。"""

    model: str
    draft_v1: str
    risks: list[dict[str, Any]]
    review_summary: str
    final_draft: str
    citations: list[dict[str, Any]]
    latency_ms: int


@observe(name="contract_draft.generate")
async def generate_full_draft(requirements: RequirementsDraft) -> GenerateResult:
    """確定済み要件を受け取り、draft → review → revise を直列実行して最終版を返す。

    各 phase で別 system プロンプトを使う (キャッシュは phase 内で効く)。
    RAG は draft phase でのみ取得し、後続 phase に同じテキストブロックとして
    流用する (再検索コストを節約)。
    """
    if not requirements.is_complete():
        raise ValueError(
            "requirements is incomplete; all 6 required fields must be filled before generate"
        )

    started = time.perf_counter()

    # ---- 1. RAG (1 度だけ) ----
    rag_query = (
        f"秘密保持契約 {requirements.purpose or ''} {requirements.confidential_info_scope or ''}"
    ).strip()
    rag_block = await _build_rag_block(rag_query)

    # 後続の generation で共有される動的入力ブロック。
    requirements_block = (
        "## 確定済み要件 (camelCase)\n"
        "```json\n"
        f"{requirements.model_dump_json(by_alias=True, indent=2)}\n"
        "```"
    )

    # ---- 2. Draft phase ----
    draft_v1 = await _run_draft_phase(requirements_block, rag_block)

    # ---- 3. Self-review phase ----
    review_summary, risks = await _run_review_phase(draft_v1, rag_block)

    # ---- 4. Revise phase ----
    final_draft = await _run_revise_phase(
        requirements_block=requirements_block,
        rag_block=rag_block,
        draft_v1=draft_v1,
        risks=risks,
    )

    return GenerateResult(
        model=settings.anthropic_model,
        draft_v1=draft_v1,
        risks=risks,
        review_summary=review_summary,
        final_draft=final_draft,
        # citations は RAG ブロックに既に整形済みで含まれているので、ここでは
        # raw 形式での再露出は省略 (UI 側はドラフト末尾の [番号] を直接参照する)。
        citations=[],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def generate_from_requirements(requirements: RequirementsDraft) -> GenerateResult:
    """eval から hearing を skip して一発生成するための薄いラッパ。

    eval 入力の golden case は「要件辞書」を直接持っており、ヒアリングを通さずに
    generate phase を測りたい (= ドラフト品質だけを評価する) ため、別エントリにしている。
    実装は ``generate_full_draft`` を呼ぶだけ。
    """
    return await generate_full_draft(requirements)


async def _run_draft_phase(requirements_block: str, rag_block: str) -> str:
    """Phase 2: 確定要件 + RAG をもとに NDA ドラフト v1 を Markdown で生成。"""
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("generate"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": requirements_block},
    ]
    if rag_block:
        system_blocks.append({"type": "text", "text": rag_block})

    response = await traced_messages_create(
        _client(),
        name="contract_draft.draft.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        messages=[
            {
                "role": "user",
                "content": (
                    "上記の確定済み要件をすべて反映した NDA (秘密保持契約書) を、"
                    "Markdown 形式で生成してください。"
                ),
            }
        ],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def _run_review_phase(draft_v1: str, rag_block: str) -> tuple[str, list[dict[str, Any]]]:
    """Phase 3: 直前のドラフトをセルフレビューし、構造化リスクを抽出。"""
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("review"),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if rag_block:
        system_blocks.append({"type": "text", "text": rag_block})

    response = await traced_messages_create(
        _client(),
        name="contract_draft.review.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        tools=[REPORT_TOOL],
        # 自由テキスト禁止: 必ず report_review を呼ばせる (構造化レスポンス保証)。
        tool_choice={"type": "tool", "name": "report_review"},
        messages=[
            {
                "role": "user",
                "content": (
                    "以下の NDA ドラフトをレビューし、"
                    "`report_review` ツールで結果を返してください。\n\n"
                    "```markdown\n"
                    f"{draft_v1}\n"
                    "```"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_review":
            payload = block.input if isinstance(block.input, dict) else {}
            return (
                str(payload.get("summary", "")),
                list(payload.get("risks", []) or []),
            )

    # tool_choice 強制下でここに来たら異常系。空レビューにフォールバック (revise が冪等になる)。
    LOG.warning("contract_draft.review did not return report_review tool_use")
    return ("", [])


async def _run_revise_phase(
    *,
    requirements_block: str,
    rag_block: str,
    draft_v1: str,
    risks: list[dict[str, Any]],
) -> str:
    """Phase 4: 検出済みリスクを system に明示して、最終版ドラフトを再生成。"""
    high_med = [r for r in risks if r.get("severity") in ("high", "medium")]
    low = [r for r in risks if r.get("severity") == "low"]

    risk_block_lines = ["## 検出リスク (high / medium)"]
    if high_med:
        for r in high_med:
            risk_block_lines.append(
                f"- **{r.get('severity', '').upper()}** "
                f"{r.get('clause', '')}: {r.get('reason', '')}"
            )
            if r.get("suggestion"):
                risk_block_lines.append(f"  - 対応方針: {r.get('suggestion')}")
    else:
        risk_block_lines.append("(該当なし)")

    risk_block_lines.append("")
    risk_block_lines.append("## 検出リスク (low)")
    if low:
        for r in low:
            risk_block_lines.append(f"- {r.get('clause', '')}: {r.get('reason', '')}")
    else:
        risk_block_lines.append("(該当なし)")

    risk_block_lines.append("")
    risk_block_lines.append("## 直前のドラフト")
    risk_block_lines.append("```markdown")
    risk_block_lines.append(draft_v1)
    risk_block_lines.append("```")
    risk_block = "\n".join(risk_block_lines)

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("revise"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": requirements_block},
    ]
    if rag_block:
        system_blocks.append({"type": "text", "text": rag_block})
    system_blocks.append({"type": "text", "text": risk_block})

    response = await traced_messages_create(
        _client(),
        name="contract_draft.revise.generation",
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        messages=[
            {
                "role": "user",
                "content": (
                    "上記の検出リスクを反映した最終版の NDA ドラフトをMarkdown で出力してください。"
                ),
            }
        ],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
