from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import voyageai

from ..config import settings


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class VoyageEmbedder:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._client = voyageai.AsyncClient(api_key=api_key or settings.voyage_api_key)
        self._model = model or settings.embedding_model
        self._batch_size = 128

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            res = await self._client.embed(
                texts=batch,
                model=self._model,
                input_type="document",
            )
            out.extend(list(v) for v in res.embeddings)
        return out


@lru_cache(maxsize=1)
def default_embedder() -> Embedder:
    return VoyageEmbedder()
