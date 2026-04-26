import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from ..config import settings
from ..rag.formatter import format_citations
from ..rag.retriever import retrieve

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "contract_review.md"
LOG = logging.getLogger(__name__)

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
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _retrieval_query(title: str, body: str) -> str:
    """契約タイトル + 本文先頭 800 字を retrieval クエリにする。"""
    head = body[:800]
    return f"{title}\n{head}"


async def _build_rag_block(title: str, body: str) -> str:
    if not settings.rag_enabled:
        return ""
    try:
        citations = await retrieve(_retrieval_query(title, body), top_k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("RAG retrieval failed; continuing without citations: %s", exc)
        return ""
    return format_citations(citations)


async def review_contract(title: str, body: str) -> dict[str, Any]:
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    rag_context = await _build_rag_block(title, body)
    if rag_context:
        system_blocks.append({"type": "text", "text": rag_context})

    response = await _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        tools=[REPORT_TOOL],
        tool_choice={"type": "tool", "name": "report_review"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"# 契約書タイトル\n{title}\n\n"
                    f"# 契約書本文\n```\n{body}\n```\n\n"
                    "上記契約書をレビューし、`report_review` ツールで結果を返してください。"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_review":
            payload = block.input
            if isinstance(payload, dict):
                return {
                    "model": response.model,
                    "summary": payload.get("summary", ""),
                    "risks": payload.get("risks", []),
                }

    raise RuntimeError("Claude did not return a tool_use block for report_review")
