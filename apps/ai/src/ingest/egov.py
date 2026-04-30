"""e-Gov 法令データを取り込んで Postgres + pgvector に保存する CLI.

このファイルが扱う AI 概念：

* **RAG ingest pipeline** — 検索可能な状態にするには、ソースを **チャンク → 埋め込み → DB** に
  通す必要がある。本 CLI はその一気通貫オーケストレータ。
  ``fetch (egov_client) → chunk (chunker) → embed (embedder) → upsert (DB)``
* **冪等な取り込み** — 同じ law_id を何度実行しても結果が壊れないよう
  ``ON CONFLICT DO UPDATE`` と「DELETE 後 INSERT（同一トランザクション）」を使う。
  これにより法令の改正反映が「再実行」で済む。
* **直列ループ** — async でも法令単位の取り込みは直列に回す。
  e-Gov の rate limit を超えない、1 件失敗が他に波及しない、ログが追える、の 3 点が理由。

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
    """allowlist テキストを読んで LawId のリストにする。

    フォーマット（``laws_allowlist.txt`` 参照）:
    - ``#`` で始まる行はコメント（無視）
    - 空行は無視
    - 行に ``#`` を含むときは、それより前を LawId として採用（行末コメント可）
    """
    ids: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 行末コメント "<id>  # 民法" 形式から LawId 部分だけを抜く。
        ids.append(line.split("#", 1)[0].strip())
    return ids


async def _upsert_document(law: FetchedLaw) -> None:
    """``law_documents`` テーブルへの **冪等 upsert**。

    ``ON CONFLICT (id) DO UPDATE`` パターンで、既存レコードがあれば更新、
    無ければ挿入する。``fetched_at`` は INSERT 時のみ now()、``updated_at`` は
    両方で now() に更新する点に注意（初回取得時刻と最終更新時刻を分けて持つ）。
    """
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
    """その法令の **既存チャンクを全削除 → 新チャンクを一括 INSERT**。

    なぜ「個別 UPSERT」ではなく「全削除 → 全挿入」なのか：
    - チャンクの境界（split 位置や ID）は ingest を回すたびに変わり得る
    - ``law_id`` 単位で「現在の正解集合」を入れ替える方が状態が単純
    - ``conn.transaction()`` 内で実行するため、途中で落ちても中途半端な
      状態にはならない（DELETE 済みでチャンク 0 件、のような事故を防ぐ）
    """
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
                # strict=True: chunks と vectors の件数不一致を即時例外で検出。
                # 片方が 1 件多い・少ないバグは沈黙するとデバッグ困難なので、
                # 早めに落とす。
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )


async def ingest_one(client: EgovClient, embedder: VoyageEmbedder, law_id: str) -> None:
    """1 つの法令について fetch → chunk → embed → upsert を直列に実行する。"""
    LOG.info("fetching %s", law_id)
    # 1) e-Gov API から XML を取得（throttle + retry は client 側で吸収）
    law = await client.fetch_law(law_id)
    # 2) Article 単位（必要に応じてスライディングウィンドウ）でチャンク化
    chunks = chunk_law(law.raw_xml)
    if not chunks:
        # XML 構造が想定外、または空の本文。スキップ（次の law_id へ）。
        LOG.warning("no chunks extracted for %s — skipping", law_id)
        return
    LOG.info("embedding %d chunks for %s (%s)", len(chunks), law_id, law.title)
    # 3) 全チャンクをバッチ埋め込み（Voyage 側で 128 件単位の内部バッチに分割）
    vectors = await embedder.embed_documents([c.body for c in chunks])
    # 4) ドキュメント本体を upsert → チャンク全置換 の順で DB 反映
    await _upsert_document(law)
    await _replace_chunks(law_id, chunks, vectors)
    LOG.info("✓ %s (%s) — %d chunks stored", law_id, law.title, len(chunks))


async def main_async(law_ids: list[str]) -> None:
    """与えられた law_id 群を **直列に** 取り込む。

    並列化したくなるが直列にする理由：
    - e-Gov API には事実上のレート制限がある（throttle で 1 req/sec）
    - 失敗したときのログが時系列で追いやすい
    - DB 側の vector index 更新が並列より直列の方が安定
    """
    embedder = VoyageEmbedder()
    async with EgovClient() as client:
        for law_id in law_ids:
            try:
                await ingest_one(client, embedder, law_id)
            except Exception as exc:  # noqa: BLE001
                # 1 件の失敗を全体停止に波及させない（残りを継続）。
                LOG.error("✗ %s failed: %s", law_id, exc)
    await close_pool()


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 引数定義。3 種の入力形式 (single / csv / allowlist) を排他で受ける。"""
    p = argparse.ArgumentParser(description="Ingest e-Gov 法令 into pgvector")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--law-id", help="single LawId, e.g. 129AC0000000089")
    g.add_argument("--law-ids", help="comma-separated LawIds")
    g.add_argument("--allowlist", type=Path, help="path to a allowlist .txt")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
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
    # asyncio.run で event loop を起動 → main_async を最後まで回して終了。
    asyncio.run(main_async(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
