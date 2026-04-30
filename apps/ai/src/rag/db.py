"""pgvector 対応 PostgreSQL コネクションプール。

このファイルが扱う AI 概念：

* **asyncpg + pgvector** — asyncpg は PostgreSQL 標準の型しか知らないので、
  ``vector`` 型を扱うには接続ごとに ``register_vector`` を呼んで
  Python の ``list[float]`` ⇄ ``vector`` の自動変換を有効化する必要がある。
* **接続プール** — リクエスト毎に new connection するとハンドシェイクで遅い。
  プールに ``min_size`` 本確保しておき、必要に応じて ``max_size`` まで増やす。
* **lazy + singleton 初期化** — FastAPI lifespan で一度だけ作って、
  以降は ``get_pool()`` 経由で取り出す。

呼び出し経路:
  ``main.py`` の lifespan → ``get_pool()`` で立ち上げ
  ``rag/retriever.py`` → ``get_pool()`` で取得
  ``ingest/egov.py`` → ``get_pool()`` で取得
"""

from __future__ import annotations

import asyncpg
from pgvector.asyncpg import register_vector

from ..config import settings

# プロセス内で 1 つだけ持つグローバルなプール。
# 複数モジュールから ``get_pool()`` で取り回す。
_pool: asyncpg.Pool | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    """プールから新しいコネクションが払い出される度に呼ばれるフック。

    asyncpg のコネクションごとに pgvector 拡張型を登録しないと、
    ``c.embedding`` 列を Python に取り出した時に型解釈に失敗する。
    """
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    """シングルトンのコネクションプールを返す（無ければ作る）。

    ``min_size=1, max_size=5`` は本リポジトリ規模での実用値。
    - min_size=1: idle でも 1 本維持して初回レイテンシを下げる
    - max_size=5: 同時実行が増えても接続数を抑えて DB 側のリソースを保護
    本番運用ならワーカー数 × 想定同時クエリ数で見直す。
    """
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=5,
            # 各 new connection 時に pgvector 型を登録するフック。
            init=_init_conn,
        )
    return _pool


async def close_pool() -> None:
    """プールを閉じる。FastAPI lifespan の shutdown フェーズで呼ばれる。"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
