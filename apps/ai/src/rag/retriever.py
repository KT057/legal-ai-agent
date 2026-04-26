from __future__ import annotations

from dataclasses import dataclass
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


async def retrieve(query: str, top_k: int | None = None) -> list[Citation]:
    if not query.strip():
        return []
    k = top_k if top_k is not None else settings.rag_top_k

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
        k,
    )
    return [
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
