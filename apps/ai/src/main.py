from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .rag.db import close_pool, get_pool
from .routers.contract_review import router as contract_review_router
from .routers.legal_chat import router as legal_chat_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.rag_enabled:
        await get_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="Legal AI Agent — AI service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(contract_review_router)
app.include_router(legal_chat_router)
