"""ReAct-style legal research agent.

Demonstrates iterative tool use: the model decides when to search the legal
corpus, what to search for, and how many times — observing tool results between
turns and refining its query before producing a final answer.

Differs from `legal_chat`:
  - legal_chat: single-shot (RAG prepended once → generate)
  - research_agent: loop (model issues `search_laws` / `read_article` calls
    repeatedly, the agent feeds results back, until the model stops calling
    tools or `max_iterations` is hit)

Useful as a study object for tool-use loops, message construction, and the
distinction between "RAG injection" and "agentic retrieval".
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropic

from ..config import settings
from ..rag.retriever import Citation, retrieve

LOG = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "あなたは日本の法務リサーチを担当する AI アシスタントです。"
    "ユーザーの質問に答えるにあたって、必要に応じて `search_laws` ツールで"
    "法令データベースを検索し、関連条文を集めてから回答してください。"
    "1 回の検索で十分でない場合は、観点を変えて複数回検索しても構いません。"
    "得られた条文を引用する際は、引用末尾に必ず `[citation_id]` を付与してください。"
    "最終回答は日本語で、結論 → 根拠条文 → 注意事項 の順に簡潔にまとめます。"
    "最終判断は弁護士・所轄官庁に確認するよう必ず添えてください。"
)

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
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _format_search_result(citations: list[Citation], offset: int) -> str:
    """Render a search result as text for the model to read."""
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
    query = str(tool_input.get("query", "")).strip()
    top_k = int(tool_input.get("top_k", settings.rag_top_k))
    top_k = max(1, min(10, top_k))
    if not query:
        return "(error: query is empty)"
    try:
        results = await retrieve(query, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("search_laws failed: %s", exc)
        return f"(error: retrieval failed: {exc})"
    offset = len(citations_seen) + 1
    citations_seen.extend(results)
    return _format_search_result(results, offset)


async def research(question: str, max_iterations: int = 5) -> dict[str, Any]:
    """Run the ReAct loop until the model produces a final answer."""
    if not question.strip():
        raise ValueError("question must not be empty")

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    citations_seen: list[Citation] = []
    started = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0
    last_model = ""

    while iterations < max_iterations:
        response = await _client().messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOLS,
            messages=messages,
        )
        last_model = response.model
        usage = getattr(response, "usage", None)
        if usage is not None:
            total_input_tokens += getattr(usage, "input_tokens", 0) or 0
            total_output_tokens += getattr(usage, "output_tokens", 0) or 0

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
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

        messages.append(
            {
                "role": "assistant",
                "content": [_block_to_dict(b) for b in response.content],
            }
        )
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            if tu.name == "search_laws":
                tool_input = tu.input if isinstance(tu.input, dict) else {}
                result_text = await _execute_search_laws(tool_input, citations_seen)
            else:
                result_text = f"(error: unknown tool: {tu.name})"
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                }
            )
        messages.append({"role": "user", "content": tool_results})
        iterations += 1

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
    """Convert an Anthropic content block to a plain dict for re-sending."""
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
