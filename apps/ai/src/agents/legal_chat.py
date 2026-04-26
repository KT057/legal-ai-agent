import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from ..config import settings
from ..rag.formatter import format_citations
from ..rag.retriever import retrieve

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "legal_chat.md"
LOG = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _build_rag_block(query: str) -> str:
    if not settings.rag_enabled or not query.strip():
        return ""
    try:
        citations = await retrieve(query, top_k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("RAG retrieval failed; continuing without citations: %s", exc)
        return ""
    return format_citations(citations)


async def reply(messages: list[ChatTurn]) -> dict[str, Any]:
    if not messages:
        raise ValueError("messages must not be empty")
    if messages[-1].role != "user":
        raise ValueError("last message must be from user")

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": _system_prompt(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    rag_context = await _build_rag_block(messages[-1].content)
    if rag_context:
        system_blocks.append({"type": "text", "text": rag_context})

    response = await _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        system=system_blocks,
        messages=[{"role": m.role, "content": m.content} for m in messages],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    return {"model": response.model, "content": text}
