"""FastAPI entrypoint: `uv run uvicorn app.main:app --reload`."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    books,
    chat,
    conversations,
    discover,
    episodes,
    index,
    jobs,
    meta,
    podcasts,
)
from app.config import get_settings
from app.db import init_db
from app.providers import ProviderNotConfigured

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().ensure_dirs()
    init_db()
    from app.jobs.worker import worker

    await worker.start()  # resumes jobs left queued/running by a previous run
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="Podcast RAG", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderNotConfigured)
async def _provider_not_configured(_: Request, exc: ProviderNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


for r in (meta, podcasts, discover, episodes, jobs, index, conversations, chat, books):
    app.include_router(r.router, prefix="/api")
