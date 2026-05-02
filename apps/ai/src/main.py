"""FastAPI アプリのエントリポイント。

このファイルが扱う AI 概念：

* **FastAPI lifespan** — アプリ起動時 / 停止時に走らせる初期化・後始末を
  ``@asynccontextmanager`` で書くモダンな書き方（旧 ``@app.on_event`` の置き換え）。
  ``yield`` の前が startup、後が shutdown に相当する。
* **DB プールのライフサイクル** — pgvector を扱う非同期コネクションプールは、
  リクエストごとに作ると遅いのでアプリ単位で 1 本確保する。
  RAG が無効なら作らない（縮退動作）。
* **ルータ合成** — エンドポイントをドメイン別（chat / research / review）に
  分けて、ここで集約マウントする。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .observability import flush_langfuse
from .rag.db import close_pool, get_pool
from .routers.contract_review import router as contract_review_router
from .routers.legal_chat import router as legal_chat_router
from .routers.research import router as research_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """アプリの起動 / 停止に紐づく副作用を集約する。

    - startup: RAG が有効なら pgvector 用の DB プールを温めておく
      （初回リクエストが「プール初期化 + 検索」の二段で遅くなるのを防ぐ）。
    - shutdown: ``finally`` の中で必ず ``close_pool()`` する。
      例外で落ちた時もコネクションを解放させたい。
    """
    if settings.rag_enabled:
        await get_pool()
    try:
        yield
    finally:
        # Langfuse はバックグラウンドスレッドで非同期送信するため、
        # プロセス終了直前に flush しないと最後の trace が落ちる。
        # ``close_pool`` より先に呼ぶ（DB プール解放中の例外で flush をスキップしないため）。
        flush_langfuse()
        await close_pool()


# title はドキュメント (/docs) に出るだけ。lifespan を渡すのが本質。
app = FastAPI(title="Legal AI Agent — AI service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """死活監視用の最軽量エンドポイント。

    意図的に DB やモデルには触れない（外部サービス障害時にも 200 を返す）。
    モニタリングは「プロセスは生きてる」だけを見るのが安全。
    """
    return {"status": "ok"}


# 各ドメインのルータをマウント。順序は OpenAPI ドキュメントの並びに影響する。
app.include_router(contract_review_router)
app.include_router(legal_chat_router)
app.include_router(research_router)
