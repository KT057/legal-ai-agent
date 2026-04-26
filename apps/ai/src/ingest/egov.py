"""e-Gov 法令データを取り込んで Postgres + pgvector に保存する CLI.

Usage:
    uv run python -m src.ingest.egov --law-id 129AC0000000089
    uv run python -m src.ingest.egov --law-ids 129AC0000000089,406AC0000000085
    uv run python -m src.ingest.egov --allowlist src/ingest/laws_allowlist.txt
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from ..rag.db import close_pool, get_pool
from .chunker import Chunk, chunk_law
from .egov_client import EgovClient, FetchedLaw
from .embedder import VoyageEmbedder

LOG = logging.getLogger("ingest.egov")


def _parse_allowlist(path: Path) -> list[str]:
    ids: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line.split("#", 1)[0].strip())
    return ids


async def _upsert_document(law: FetchedLaw) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO law_documents (
          id, law_num, title, law_type, promulgation_date, source_url, raw_xml,
          fetched_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5::date, $6, $7, now(), now())
        ON CONFLICT (id) DO UPDATE SET
          law_num = EXCLUDED.law_num,
          title = EXCLUDED.title,
          law_type = EXCLUDED.law_type,
          promulgation_date = EXCLUDED.promulgation_date,
          source_url = EXCLUDED.source_url,
          raw_xml = EXCLUDED.raw_xml,
          updated_at = now()
        """,
        law.law_id,
        law.law_num,
        law.title,
        law.law_type,
        law.promulgation_date,
        law.source_url,
        law.raw_xml,
    )


async def _replace_chunks(law_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM law_chunks WHERE law_id = $1", law_id)
        await conn.executemany(
            """
            INSERT INTO law_chunks (
              law_id, article_no, article_title, body, token_count, embedding
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (
                    law_id,
                    chunk.article_no,
                    chunk.article_title,
                    chunk.body,
                    chunk.token_count,
                    vector,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )


async def ingest_one(client: EgovClient, embedder: VoyageEmbedder, law_id: str) -> None:
    LOG.info("fetching %s", law_id)
    law = await client.fetch_law(law_id)
    chunks = chunk_law(law.raw_xml)
    if not chunks:
        LOG.warning("no chunks extracted for %s — skipping", law_id)
        return
    LOG.info("embedding %d chunks for %s (%s)", len(chunks), law_id, law.title)
    vectors = await embedder.embed_documents([c.body for c in chunks])
    await _upsert_document(law)
    await _replace_chunks(law_id, chunks, vectors)
    LOG.info("✓ %s (%s) — %d chunks stored", law_id, law.title, len(chunks))


async def main_async(law_ids: list[str]) -> None:
    embedder = VoyageEmbedder()
    async with EgovClient() as client:
        for law_id in law_ids:
            try:
                await ingest_one(client, embedder, law_id)
            except Exception as exc:  # noqa: BLE001
                LOG.error("✗ %s failed: %s", law_id, exc)
    await close_pool()


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest e-Gov 法令 into pgvector")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--law-id", help="single LawId, e.g. 129AC0000000089")
    g.add_argument("--law-ids", help="comma-separated LawIds")
    g.add_argument("--allowlist", type=Path, help="path to a allowlist .txt")
    p.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if args.law_id:
        ids = [args.law_id]
    elif args.law_ids:
        ids = [s.strip() for s in args.law_ids.split(",") if s.strip()]
    else:
        ids = _parse_allowlist(args.allowlist)
    if not ids:
        LOG.error("no law ids resolved")
        return 2
    asyncio.run(main_async(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
