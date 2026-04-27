"""Unit test for the retriever — mocks Voyage and asyncpg pool."""

from __future__ import annotations

import pytest

from src.rag import db, retriever
from src.rag.retriever import Citation


class _FakePool:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def fetch(self, _sql: str, _embedding, _k):  # noqa: ANN001
        return self._rows


class _FakeVoyageResult:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings


class _FakeVoyage:
    async def embed(self, texts, model, input_type):  # noqa: ANN001
        assert input_type == "query"
        return _FakeVoyageResult([[0.1] * 1024 for _ in texts])


@pytest.fixture(autouse=True)
def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "law_id": "129AC0000000089",
            "law_title": "民法",
            "law_num": "明治二十九年法律第八十九号",
            "source_url": "https://laws.e-gov.go.jp/law/129AC0000000089",
            "article_no": "第七百九条",
            "article_title": "（不法行為による損害賠償）",
            "body": "故意又は過失によって…",
            "score": 0.87,
        }
    ]
    fake_pool = _FakePool(rows)

    async def _fake_get_pool():
        return fake_pool

    monkeypatch.setattr(db, "get_pool", _fake_get_pool)
    monkeypatch.setattr(retriever, "get_pool", _fake_get_pool)

    retriever._voyage.cache_clear()
    monkeypatch.setattr(retriever, "_voyage", lambda: _FakeVoyage())


async def test_retrieve_returns_citations() -> None:
    cites = await retriever.retrieve("不法行為とは", top_k=3)
    assert len(cites) == 1
    cite = cites[0]
    assert isinstance(cite, Citation)
    assert cite.law_id == "129AC0000000089"
    assert cite.article_no == "第七百九条"
    assert cite.score == pytest.approx(0.87)


async def test_retrieve_empty_query_returns_empty() -> None:
    assert await retriever.retrieve("   ", top_k=3) == []
