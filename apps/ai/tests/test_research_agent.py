"""Tests for the ReAct research agent.

Verifies the loop: model emits tool_use → agent executes → result is fed
back as a `tool_result` user message → model produces final text.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents import research_agent
from src.rag.retriever import Citation


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_id: str, name: str, tool_input: dict[str, Any]) -> None:
        self.id = tool_id
        self.name = name
        self.input = tool_input


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Usage:
    def __init__(self, in_tokens: int, out_tokens: int) -> None:
        self.input_tokens = in_tokens
        self.output_tokens = out_tokens


class _Response:
    def __init__(self, content: list[Any], model: str = "claude-test") -> None:
        self.content = content
        self.model = model
        self.usage = _Usage(10, 5)


class _Messages:
    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return self._scripted.pop(0)


class _Client:
    def __init__(self, scripted: list[_Response]) -> None:
        self.messages = _Messages(scripted)


async def test_research_agent_runs_loop_and_returns_final_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Round 1: model asks to search → Round 2: model produces final text.
    scripted = [
        _Response(
            content=[_ToolUseBlock("tool_1", "search_laws", {"query": "36協定", "top_k": 3})]
        ),
        _Response(content=[_TextBlock("36協定は労働基準法36条…[citation_id=1]")]),
    ]
    fake = _Client(scripted)
    research_agent._client.cache_clear()
    monkeypatch.setattr(research_agent, "_client", lambda: fake)

    async def _fake_retrieve(query: str, top_k: int):  # noqa: ANN001
        assert query == "36協定"
        return [
            Citation(
                law_id="322AC0000000049",
                law_title="労働基準法",
                law_num="昭和二十二年法律第四十九号",
                article_no="第三十六条",
                article_title="（時間外及び休日の労働）",
                body="使用者は、労使協定をし…",
                source_url="https://laws.e-gov.go.jp/law/322AC0000000049",
                score=0.91,
            )
        ]

    monkeypatch.setattr(research_agent, "retrieve", _fake_retrieve)

    result = await research_agent.research("36協定とは?", max_iterations=3)

    assert result["iterations"] == 1
    assert "36協定" in result["content"]
    assert result["model"] == "claude-test"
    assert len(result["citations"]) == 1
    assert result["usage"]["input_tokens"] == 20  # 2 calls × 10
    # 2nd API call should have received a tool_result message.
    second_call = fake.messages.calls[1]
    last_user = second_call["messages"][-1]
    assert last_user["role"] == "user"
    assert isinstance(last_user["content"], list)
    assert last_user["content"][0]["type"] == "tool_result"
    assert "労働基準法" in last_user["content"][0]["content"]


async def test_research_agent_stops_at_max_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Always returns tool_use → never converges.
    def make_tool_call() -> _Response:
        return _Response(content=[_ToolUseBlock("tool_x", "search_laws", {"query": "x"})])

    fake = _Client([make_tool_call() for _ in range(10)])
    research_agent._client.cache_clear()
    monkeypatch.setattr(research_agent, "_client", lambda: fake)

    async def _fake_retrieve(query: str, top_k: int):  # noqa: ANN001
        return []

    monkeypatch.setattr(research_agent, "retrieve", _fake_retrieve)

    result = await research_agent.research("無限ループ", max_iterations=2)
    assert result["iterations"] == 2
    assert "max_iterations" in result["content"]


async def test_research_agent_rejects_empty_question() -> None:
    with pytest.raises(ValueError):
        await research_agent.research("   ")
