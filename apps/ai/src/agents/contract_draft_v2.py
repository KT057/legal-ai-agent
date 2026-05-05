"""NDA ドラフト生成エージェント — LangGraph (StateGraph) 版。

このファイルは ``contract_draft.py`` (v1: Anthropic SDK 直叩き) と **同じワークフロー**
(hearing → draft → review → revise) を **LangGraph (StateGraph)** で書き直した v2 実装。
既存の v1 と並べて読めるよう、入出力 Pydantic 型 / プロンプト / RAG / Langfuse trace 名以外の
基本パターンは v1 を流用しつつ、フロー制御だけ「declarative DAG」に変えている。

このファイルが扱う AI 概念：

* **StateGraph** — TypedDict で定義された state を node 間で受け渡す declarative graph。
  v1 では Python の ``await`` 列で順次実行していた処理を、ノードとエッジに分解する。
* **conditional_edges** — node の出力に応じて次の遷移先を実行時に選ぶ。v2 では
  revise 後にリスク残量を見て「もう 1 度 revise を回すか / END に行くか」を分岐させ、
  LangGraph の真価 (循環 + 条件) を 1 ヶ所で見せる。
* **bind_tools** + ``tool_choice`` — ``ChatAnthropic.bind_tools(...)`` で OpenAI/Anthropic
  互換のツールスキーマを束ね、``tool_choice="any"`` や ``{"type":"tool","name":...}`` で
  v1 と等価な振る舞いを実現する。返ってくる ``AIMessage.tool_calls`` は
  ``[{"id":..., "name":..., "args": {...}}]`` の形 (v1 の ``block.input`` と微妙に異なる)。
* **System prompt + Prompt cache** — ``SystemMessage(content=[{...}, {...}])`` で
  リスト形式の content を渡すと、Anthropic 側に各ブロックがそのまま伝わるので
  ``cache_control: ephemeral`` が機能する (v1 と同じ静的/動的の 2 ブロック構造を維持)。

呼び出し経路：

* ``routers/contract_draft_v2.py`` (POST /draft-v2/hearing)  → ``hearing_turn_v2()``
* ``routers/contract_draft_v2.py`` (POST /draft-v2/generate) → ``generate_full_draft_v2()``
* eval ハーネス → ``generate_from_requirements_v2()`` (hearing スキップで一発生成)

注意：プロンプト 4 本 (``prompts/contract_draft_*.md``) と
``RequirementsDraft`` / ``HEARING_TOOLS`` / ``REPORT_TOOL`` は v1 から **そのまま再利用** する
(同じ仕様を 2 ヶ所に書くのを避けるため)。
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import settings
from ..observability import observe
from .contract_draft import (
    _FIELD_LABELS_JA,
    _REQUIRED_FIELDS,
    HEARING_TOOLS,
    REPORT_TOOL,
    GenerateResult,
    HearingTurnInput,
    HearingTurnResult,
    RequirementsDraft,
    _build_rag_block,
    _system_prompt,
    _truthy,
)

LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _llm() -> ChatAnthropic:
    """ChatAnthropic シングルトン。

    ``ChatAnthropic`` は内部で ``anthropic.AsyncAnthropic`` を握っているので、
    プロセス内 1 つに統一してコネクションプールを使い回す。
    """
    # type: ignore[call-arg] — ChatAnthropic は実行時 BaseModel なので静的解析が弱い
    return ChatAnthropic(
        model=settings.anthropic_model,  # type: ignore[call-arg]
        max_tokens=settings.max_tokens,
        api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────
# Hearing graph (1 node)
# ─────────────────────────────────────────────────────────────


class HearingState(TypedDict):
    """Hearing graph の state。

    LangGraph の state は **node が値を読み書きする中央ハブ**。
    入力は外側から ainvoke(state) で渡され、最後の node が更新したものが
    final_state として返る。フィールドの型は TypedDict で宣言する
    (Pydantic 互換、LangGraph が dict として扱う)。
    """

    # ─ 入力 ─
    requirements_in: dict[str, Any]
    user_message: str
    history: list[dict[str, str]]
    # ─ 出力 ─
    requirements_out: dict[str, Any]
    assistant_message: str
    is_complete: bool
    pending_question: str | None
    missing_field: str | None
    model: str


async def hearing_node(state: HearingState) -> dict[str, Any]:
    """ヒアリング 1 ターン分を 1 node で完結させる。

    v1 の ``hearing_turn`` と同じロジックを LangChain ラッパー越しに実装。
    返り値は state の **差分 (partial dict)**。LangGraph が自動で merge する。
    """
    current_block = (
        "## 現在の要件 (camelCase)\n"
        "```json\n"
        f"{json.dumps(state['requirements_in'], ensure_ascii=False, indent=2)}\n"
        "```"
    )

    # SystemMessage は content にリストを渡すと multi-block システムプロンプトになる。
    # cache_control は Anthropic native のキー名で書けば adapter が透過に伝える。
    system_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("hearing"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": current_block},
    ]

    messages: list[Any] = [SystemMessage(content=system_content)]
    for h in state["history"]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=state["user_message"]))

    # bind_tools(...) で「ツール束ねた runnable」を作る。
    # tool_choice="any" は「いずれかのツールを必ず呼ぶ」を意味する Anthropic の指示
    # (v1 では tool_choice={"type": "any"} と書いていた; LangChain では文字列で渡せる)。
    llm_with_tools = _llm().bind_tools(HEARING_TOOLS, tool_choice="any")
    response = await llm_with_tools.ainvoke(messages)

    incoming_req = RequirementsDraft.model_validate(state["requirements_in"])
    pending_q: str | None = None
    missing_f: str | None = None

    # langchain-anthropic は AIMessage.tool_calls に
    # [{"id": ..., "name": ..., "args": {...}}, ...] の形で詰めて返す。
    # v1 で見ていた ``block.input`` は ``tool_calls[i]["args"]`` に対応する。
    tool_calls = getattr(response, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args", {}) or {}
        if name == "update_requirements":
            try:
                new_req = RequirementsDraft.model_validate(args)
                incoming_req = incoming_req.merge(new_req)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("[v2] update_requirements parse failed: %s", exc)
        elif name == "ask_user":
            pending_q = str(args.get("question", "")).strip() or None
            missing_f = str(args.get("missingField", "")).strip() or None

    completed = incoming_req.is_complete()

    if completed:
        msg = (
            "必要な要件はすべて確認できました。"
            "右側の「ドラフトを生成」ボタンを押すと、最初のドラフトが生成されます。"
        )
    elif pending_q:
        msg = pending_q
    else:
        next_missing = next(
            (n for n in _REQUIRED_FIELDS if not _truthy(getattr(incoming_req, n))),
            None,
        )
        if next_missing:
            label = _FIELD_LABELS_JA.get(next_missing, next_missing or "")
            msg = f"続けて、{label}について教えてください。"
        else:
            msg = "もう少し詳しく教えてください。"

    # 部分 dict を返すと LangGraph が state にマージしてくれる。
    return {
        "requirements_out": incoming_req.model_dump(by_alias=True),
        "assistant_message": msg,
        "is_complete": completed,
        "pending_question": pending_q,
        "missing_field": missing_f,
        "model": settings.anthropic_model,
    }


@lru_cache(maxsize=1)
def _hearing_graph() -> Any:
    """Hearing graph をビルドして compile したものを singleton で持つ。

    ```
    START → hearing → END
    ```

    これは StateGraph の最小構成サンプルにもなっている。
    """
    g: StateGraph = StateGraph(HearingState)
    g.add_node("hearing", hearing_node)
    g.add_edge(START, "hearing")
    g.add_edge("hearing", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────
# Generate graph (draft → review → revise → [conditional revise])
# ─────────────────────────────────────────────────────────────


class GenerateState(TypedDict):
    # ─ 入力 ─
    requirements: dict[str, Any]
    rag_block: str
    # ─ 中間/最終生成物 ─
    draft_v1: str
    risks: list[dict[str, Any]]
    review_summary: str
    final_draft: str
    # ─ 制御 ─
    revise_count: int
    model: str


async def draft_node(state: GenerateState) -> dict[str, Any]:
    """Phase 2: draft v1 (初版) を Markdown で生成。"""
    req_block = (
        "## 確定済み要件 (camelCase)\n"
        "```json\n"
        f"{json.dumps(state['requirements'], ensure_ascii=False, indent=2)}\n"
        "```"
    )
    system_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("generate"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": req_block},
    ]
    if state["rag_block"]:
        system_content.append({"type": "text", "text": state["rag_block"]})

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(
            content=(
                "上記の確定済み要件をすべて反映した NDA (秘密保持契約書) を、"
                "Markdown 形式で生成してください。"
            )
        ),
    ]
    response = await _llm().ainvoke(messages)
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"draft_v1": text.strip(), "model": settings.anthropic_model}


async def review_node(state: GenerateState) -> dict[str, Any]:
    """Phase 3: ドラフトをセルフレビューして構造化リスクを抽出。

    ``REPORT_TOOL`` を ``tool_choice={"type":"tool","name":"report_review"}`` で
    強制呼び出しすることで、自由テキストでなく必ず構造化レスポンスにする。
    """
    system_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("review"),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if state["rag_block"]:
        system_content.append({"type": "text", "text": state["rag_block"]})

    user_content = (
        "以下の NDA ドラフトをレビューし、`report_review` ツールで結果を返してください。"
        "\n\n"
        "```markdown\n"
        f"{state['draft_v1']}\n"
        "```"
    )
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    llm_with_tool = _llm().bind_tools(
        [REPORT_TOOL],
        tool_choice={"type": "tool", "name": "report_review"},
    )
    response = await llm_with_tool.ainvoke(messages)

    risks: list[dict[str, Any]] = []
    summary = ""
    for tc in getattr(response, "tool_calls", None) or []:
        if tc.get("name") == "report_review":
            args = tc.get("args", {}) or {}
            summary = str(args.get("summary", ""))
            risks = list(args.get("risks", []) or [])
            break

    if not summary and not risks:
        # tool_choice 強制下でここに来ることはほぼないが、空レビューにフォールバック
        # (後続の revise が冪等に動けるよう)。
        LOG.warning("[v2] review_node: report_review tool_call not found in response")

    return {"risks": risks, "review_summary": summary}


async def revise_node(state: GenerateState) -> dict[str, Any]:
    """Phase 4: 検出されたリスクを反映した最終版を生成。

    2 周目以降は ``state['final_draft']`` を「直前のドラフト」として使う
    (= 前ターンの revise 出力の上にさらに改善を重ねる)。
    """
    risks = state["risks"]
    high_med = [r for r in risks if r.get("severity") in ("high", "medium")]
    low = [r for r in risks if r.get("severity") == "low"]

    risk_lines: list[str] = ["## 検出リスク (high / medium)"]
    if high_med:
        for r in high_med:
            risk_lines.append(
                f"- **{(r.get('severity') or '').upper()}** "
                f"{r.get('clause', '')}: {r.get('reason', '')}"
            )
            if r.get("suggestion"):
                risk_lines.append(f"  - 対応方針: {r.get('suggestion')}")
    else:
        risk_lines.append("(該当なし)")
    risk_lines.append("")
    risk_lines.append("## 検出リスク (low)")
    if low:
        for r in low:
            risk_lines.append(f"- {r.get('clause', '')}: {r.get('reason', '')}")
    else:
        risk_lines.append("(該当なし)")
    risk_lines.append("")
    risk_lines.append("## 直前のドラフト")
    risk_lines.append("```markdown")
    # 2 周目以降は前ターンの最終版を起点にする (= 改善を重ねる動き)
    base_draft = state.get("final_draft") or state["draft_v1"]
    risk_lines.append(base_draft)
    risk_lines.append("```")

    req_block = (
        "## 確定済み要件 (camelCase)\n"
        "```json\n"
        f"{json.dumps(state['requirements'], ensure_ascii=False, indent=2)}\n"
        "```"
    )

    system_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt("revise"),
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": req_block},
    ]
    if state["rag_block"]:
        system_content.append({"type": "text", "text": state["rag_block"]})
    system_content.append({"type": "text", "text": "\n".join(risk_lines)})

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(
            content=(
                "上記の検出リスクを反映した最終版の NDA ドラフトをMarkdown で出力してください。"
            )
        ),
    ]
    response = await _llm().ainvoke(messages)
    text = response.content if isinstance(response.content, str) else str(response.content)

    return {
        "final_draft": text.strip(),
        "revise_count": state.get("revise_count", 0) + 1,
    }


def should_loop(state: GenerateState) -> str:
    """Conditional edge: revise の後に再 revise するか END に行くか決める。

    LangGraph の真価が出る箇所。v1 (直接 SDK 版) ではこの種の「もう 1 周回す」
    制御を ``while`` や ``if`` で書く必要があったが、ここでは state を見て
    遷移先を文字列で返すだけで済む (= グラフの形は変わらず、判定だけ差し替えられる)。

    判定方針:
      - revise_count >= 2 で必ず END (暴走防止)
      - high が 1 件以上、または medium が 5 件以上なら品質懸念ありと判断し再 revise
      - そうでなければ END
    """
    if state.get("revise_count", 0) >= 2:
        return END
    risks = state.get("risks", [])
    high = sum(1 for r in risks if r.get("severity") == "high")
    medium = sum(1 for r in risks if r.get("severity") == "medium")
    if high >= 1 or medium >= 5:
        return "revise"
    return END


@lru_cache(maxsize=1)
def _generate_graph() -> Any:
    """Generate graph をビルドして compile したものを singleton で持つ。

    ```
    START → draft → review → revise ─┐
                                  ↑   ↓
                                  └── (cond: high/medium が多ければ再 revise) ──┐
                                                                                 │
                                                                                END
    ```
    """
    g: StateGraph = StateGraph(GenerateState)
    g.add_node("draft", draft_node)
    g.add_node("review", review_node)
    g.add_node("revise", revise_node)
    g.add_edge(START, "draft")
    g.add_edge("draft", "review")
    g.add_edge("review", "revise")
    # conditional_edges: revise 出力後の遷移先を should_loop が決める
    g.add_conditional_edges("revise", should_loop, {"revise": "revise", END: END})
    return g.compile()


# ─────────────────────────────────────────────────────────────
# Public API (v1 と同じシグネチャを返すラッパ)
# ─────────────────────────────────────────────────────────────


@observe(name="contract_draft_v2.hearing")
async def hearing_turn_v2(payload: HearingTurnInput) -> HearingTurnResult:
    """Hearing 1 ターンを LangGraph で進める。戻り型は v1 と完全互換。"""
    if not payload.user_message.strip():
        raise ValueError("user_message must not be empty")

    initial: HearingState = {
        "requirements_in": payload.current_requirements.model_dump(by_alias=True),
        "user_message": payload.user_message,
        "history": payload.history,
        "requirements_out": {},
        "assistant_message": "",
        "is_complete": False,
        "pending_question": None,
        "missing_field": None,
        "model": "",
    }
    final_state: HearingState = await _hearing_graph().ainvoke(initial)

    return HearingTurnResult(
        model=final_state["model"],
        assistant_message=final_state["assistant_message"],
        requirements=RequirementsDraft.model_validate(final_state["requirements_out"]),
        is_complete=final_state["is_complete"],
        pending_question=final_state["pending_question"],
        missing_field=final_state["missing_field"],
    )


@observe(name="contract_draft_v2.generate")
async def generate_full_draft_v2(requirements: RequirementsDraft) -> GenerateResult:
    """Generate (draft → review → revise [→ revise]) を LangGraph で実行。"""
    if not requirements.is_complete():
        raise ValueError(
            "requirements is incomplete; all 6 required fields must be filled before generate"
        )

    started = time.perf_counter()
    rag_query = (
        f"秘密保持契約 {requirements.purpose or ''} {requirements.confidential_info_scope or ''}"
    ).strip()
    rag_block = await _build_rag_block(rag_query)

    initial: GenerateState = {
        "requirements": requirements.model_dump(by_alias=True),
        "rag_block": rag_block,
        "draft_v1": "",
        "risks": [],
        "review_summary": "",
        "final_draft": "",
        "revise_count": 0,
        "model": settings.anthropic_model,
    }
    final_state: GenerateState = await _generate_graph().ainvoke(initial)

    return GenerateResult(
        model=final_state.get("model") or settings.anthropic_model,
        draft_v1=final_state["draft_v1"],
        risks=final_state["risks"],
        review_summary=final_state["review_summary"],
        final_draft=final_state["final_draft"],
        citations=[],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


async def generate_from_requirements_v2(requirements: RequirementsDraft) -> GenerateResult:
    """eval から hearing を skip して一発生成するラッパ (v1 と同名で v2 用)。"""
    return await generate_full_draft_v2(requirements)
