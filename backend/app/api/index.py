"""Vector index statistics and background rebuild endpoints."""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models import Episode, Job, Podcast
from app.schemas import IndexStats, JobOut
from app.services.vectorstore import get_vector_store

router = APIRouter(tags=["index"])

SessionDep = Annotated[Session, Depends(get_session)]


def _invoke_job_to_out(job_to_out_fn: Any, session: Session, job: Job) -> JobOut:
    params = list(inspect.signature(job_to_out_fn).parameters.values())
    positional = [
        p
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2 and positional[0].name in ("session", "db", "s"):
        return job_to_out_fn(session, job)
    if len(positional) >= 2 and positional[1].name in ("session", "db", "s"):
        return job_to_out_fn(job, session)
    return job_to_out_fn(job)


@router.get("/index/stats", response_model=IndexStats)
def get_index_stats(session: SessionDep) -> IndexStats:
    """Return podcast, episode, passage, and duration statistics for the active index."""
    settings = get_settings()
    podcasts_count = int(session.exec(select(func.count()).select_from(Podcast)).one())
    episodes_total = int(session.exec(select(func.count()).select_from(Episode)).one())

    indexed_rows = session.exec(select(Episode).where(col(Episode.indexed_at).is_not(None))).all()
    episodes_indexed = len(indexed_rows)
    total_seconds = sum(ep.duration_seconds or 0 for ep in indexed_rows)
    hours_indexed = round(total_seconds / 3600.0, 2)
    passages = get_vector_store().count()

    return IndexStats(
        podcasts=podcasts_count,
        episodes_total=episodes_total,
        episodes_indexed=episodes_indexed,
        passages=passages,
        embedding_model=settings.embedding_id,
        hours_indexed=hours_indexed,
    )


@router.post("/index/rebuild", response_model=JobOut)
def rebuild_index_endpoint(session: SessionDep) -> JobOut:
    """Enqueue a background job to rebuild the vector index from existing transcripts."""
    from app.jobs import worker as worker_mod

    job = Job(kind="rebuild_index")
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.id is not None
    worker_mod.worker.enqueue(job.id)
    return _invoke_job_to_out(worker_mod.job_to_out, session, job)
