"""Verify the reranker path: over-fetch → rerank → take top K with new scores."""

from __future__ import annotations

from typing import Any

import pytest

from src.rag import db, retriever
from src.rag.retriever import Citation


def _row(law_id: str, score: float) -> dict[str, Any]:
    return {
        "law_id": law_id,
        "law_title": f"法令-{law_id}",
        "law_num": "test",
        "source_url": f"https://example/{law_id}",
        "article_no": "第一条",
        "article_title": None,
        "body": f"body of {law_id}",
        "score": score,
    }


class _FakePool:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.last_limit: int | None = None

    async def fetch(self, _sql: str, _embedding, k: int):  # noqa: ANN001
        self.last_limit = k
        return self._rows[:k]


class _RerankResult:
    def __init__(self, index: int, score: float) -> None:
        self.index = index
        self.relevance_score = score


class _RerankResponse:
    def __init__(self, results: list[_RerankResult]) -> None:
        self.results = results


class _FakeVoyageWithRerank:
    def __init__(self) -> None:
        self.rerank_called_with: dict[str, Any] | None = None

    async def embed(self, texts, model, input_type):  # noqa: ANN001
        class _Res:
            embeddings = [[0.1] * 1024 for _ in texts]

        return _Res()

    async def rerank(self, query, documents, model, top_k):  # noqa: ANN001
        self.rerank_called_with = {
            "query": query,
            "documents_count": len(documents),
            "model": model,
            "top_k": top_k,
        }
        # Reverse order: the LAST candidate is now scored highest.
        n = len(documents)
        return _RerankResponse(
            [_RerankResult(index=n - 1 - i, score=1.0 - i * 0.1) for i in range(top_k)]
        )


async def test_rerank_overfetches_and_reorders(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row(f"L{i:03d}", 0.5 + i * 0.01) for i in range(15)]
    fake_pool = _FakePool(rows)
    fake_voyage = _FakeVoyageWithRerank()

    async def _fake_get_pool():
        return fake_pool

    monkeypatch.setattr(db, "get_pool", _fake_get_pool)
    monkeypatch.setattr(retriever, "get_pool", _fake_get_pool)
    retriever._voyage.cache_clear()
    monkeypatch.setattr(retriever, "_voyage", lambda: fake_voyage)
    monkeypatch.setattr(retriever.settings, "rerank_enabled", True)
    monkeypatch.setattr(retriever.settings, "rerank_candidate_multiplier", 3)
    monkeypatch.setattr(retriever.settings, "rerank_model", "rerank-2")

    cites = await retriever.retrieve("test query", top_k=5)

    # Over-fetched 5 * 3 = 15 candidates.
    assert fake_pool.last_limit == 15
    # Reranker received all 15.
    assert fake_voyage.rerank_called_with is not None
    assert fake_voyage.rerank_called_with["documents_count"] == 15
    assert fake_voyage.rerank_called_with["top_k"] == 5
    # Got 5 reranked citations.
    assert len(cites) == 5
    assert all(isinstance(c, Citation) for c in cites)
    # Score is the rerank score, not the dense score.
    assert cites[0].score == pytest.approx(1.0)
    # Reverse order: last candidate (L014) ranked highest.
    assert cites[0].law_id == "L014"


async def test_rerank_disabled_skips_voyage_rerank(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row(f"L{i:03d}", 0.9 - i * 0.05) for i in range(5)]
    fake_pool = _FakePool(rows)
    fake_voyage = _FakeVoyageWithRerank()

    async def _fake_get_pool():
        return fake_pool

    monkeypatch.setattr(db, "get_pool", _fake_get_pool)
    monkeypatch.setattr(retriever, "get_pool", _fake_get_pool)
    retriever._voyage.cache_clear()
    monkeypatch.setattr(retriever, "_voyage", lambda: fake_voyage)
    monkeypatch.setattr(retriever.settings, "rerank_enabled", False)

    cites = await retriever.retrieve("q", top_k=3)
    assert fake_pool.last_limit == 3  # no over-fetch when rerank off
    assert fake_voyage.rerank_called_with is None
    assert len(cites) == 3
    # Dense scores preserved.
    assert cites[0].score == pytest.approx(0.9)
