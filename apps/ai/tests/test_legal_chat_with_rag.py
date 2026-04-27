"""Verify RAG injection: system block 0 cached, block 1 (RAG) NOT cached."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents import legal_chat
from src.agents.legal_chat import ChatTurn
from src.rag.retriever import Citation


class _FakeBlock:
    type = "text"
    text = "OK"


class _FakeResponse:
    model = "claude-test"
    content = [_FakeBlock()]


class _FakeMessages:
    def __init__(self) -> None:
        self.last_call: dict[str, Any] | None = None

    async def create(self, **kwargs):  # noqa: ANN003
        self.last_call = kwargs
        return _FakeResponse()


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


async def test_rag_injects_uncached_second_system_block(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeAnthropic()
    legal_chat._client.cache_clear()
    monkeypatch.setattr(legal_chat, "_client", lambda: fake_client)
    monkeypatch.setattr(legal_chat.settings, "rag_enabled", True)

    async def _fake_retrieve(query: str, top_k: int):  # noqa: ANN001
        return [
            Citation(
                law_id="129AC0000000089",
                law_title="民法",
                law_num="明治二十九年法律第八十九号",
                article_no="第七百九条",
                article_title="（不法行為による損害賠償）",
                body="故意又は過失によって他人の権利…",
                source_url="https://laws.e-gov.go.jp/law/129AC0000000089",
                score=0.9,
            )
        ]

    monkeypatch.setattr(legal_chat, "retrieve", _fake_retrieve)

    await legal_chat.reply([ChatTurn(role="user", content="不法行為とは？")])

    call = fake_client.messages.last_call
    assert call is not None
    system = call["system"]
    assert isinstance(system, list)
    assert len(system) == 2

    # Block 0: static prompt, ephemeral cache.
    assert system[0]["cache_control"] == {"type": "ephemeral"}

    # Block 1: dynamic RAG payload, MUST NOT be cached (else cache invalidates per request).
    assert "cache_control" not in system[1]
    assert "## 参考法令" in system[1]["text"]
    assert "[1]" in system[1]["text"]
    assert "民法" in system[1]["text"]


async def test_rag_disabled_skips_second_block(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeAnthropic()
    legal_chat._client.cache_clear()
    monkeypatch.setattr(legal_chat, "_client", lambda: fake_client)
    monkeypatch.setattr(legal_chat.settings, "rag_enabled", False)

    await legal_chat.reply([ChatTurn(role="user", content="質問")])

    call = fake_client.messages.last_call
    assert call is not None
    assert len(call["system"]) == 1
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
