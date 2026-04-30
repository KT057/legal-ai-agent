from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import voyageai

from ..config import settings
from .db import get_pool


@dataclass(frozen=True, slots=True)
class Citation:
    law_id: str
    law_title: str
    law_num: str
    article_no: str | None
    article_title: str | None
    body: str
    source_url: str
    score: float


@lru_cache(maxsize=1)
def _voyage() -> voyageai.AsyncClient:
    return voyageai.AsyncClient(api_key=settings.voyage_api_key)


async def _embed_query(query: str) -> list[float]:
    res = await _voyage().embed(
        texts=[query],
        model=settings.embedding_model,
        input_type="query",
    )
    return list(res.embeddings[0])


async def _rerank(query: str, candidates: list[Citation], top_k: int) -> list[Citation]:
    """Rerank dense-retrieval candidates with Voyage rerank-2.

    The dense search optimizes for semantic similarity to the *embedding* of
    the query, but rerankers cross-encode the query and each candidate
    document jointly — typically much higher precision at the top, at the
    cost of a second API call. We over-fetch candidates (multiplier),
    rerank, then take the top K.
    """
    if not candidates:
        return candidates
    res = await _voyage().rerank(
        query=query,
        documents=[c.body for c in candidates],
        model=settings.rerank_model,
        top_k=top_k,
    )
    return [replace(candidates[r.index], score=float(r.relevance_score)) for r in res.results]


async def retrieve(query: str, top_k: int | None = None) -> list[Citation]:
    if not query.strip():
        return []
    k = top_k if top_k is not None else settings.rag_top_k
    candidate_k = k * settings.rerank_candidate_multiplier if settings.rerank_enabled else k

    embedding = await _embed_query(query)
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
          d.id            AS law_id,
          d.title         AS law_title,
          d.law_num       AS law_num,
          d.source_url    AS source_url,
          c.article_no    AS article_no,
          c.article_title AS article_title,
          c.body          AS body,
          1 - (c.embedding <=> $1) AS score
        FROM law_chunks AS c
        JOIN law_documents AS d ON d.id = c.law_id
        ORDER BY c.embedding <=> $1
        LIMIT $2
        """,
        embedding,
        candidate_k,
    )
    candidates = [
        Citation(
            law_id=row["law_id"],
            law_title=row["law_title"],
            law_num=row["law_num"],
            article_no=row["article_no"],
            article_title=row["article_title"],
            body=row["body"],
            source_url=row["source_url"],
            score=float(row["score"]),
        )
        for row in rows
    ]

    if settings.rerank_enabled and candidates:
        return await _rerank(query, candidates, k)
    return candidates
