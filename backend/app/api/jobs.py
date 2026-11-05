"""Background job listing, inspection, cancellation, and retry endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.db import get_session
from app.jobs.worker import job_to_out, worker
from app.models import Job
from app.schemas import JobOut

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
_ACTIVE_STATUSES = ("queued", "running")


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    session: SessionDep,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobOut]:
    """List background jobs newest first, optionally filtered by comma-separated status."""
    stmt = select(Job)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            stmt = stmt.where(col(Job.status).in_(statuses))
    stmt = stmt.order_by(col(Job.created_at).desc(), col(Job.id).desc()).limit(limit)
    jobs = session.exec(stmt).all()
    return [job_to_out(session, job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: SessionDep) -> JobOut:
    """Fetch a single job by ID."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_out(session, job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, session: SessionDep) -> JobOut:
    """Cancel a queued or running job."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    worker.cancel(job_id)
    session.expire_all()
    updated = session.get(Job, job_id)
    assert updated is not None
    return job_to_out(session, updated)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, session: SessionDep) -> JobOut:
    """Create and enqueue a new job with the same kind, episode, and steps."""
    old_job = session.get(Job, job_id)
    if old_job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if old_job.episode_id is not None:
        active = session.exec(
            select(Job).where(
                Job.episode_id == old_job.episode_id,
                col(Job.status).in_(_ACTIVE_STATUSES),
            )
        ).first()
        if active is not None:
            return job_to_out(session, active)

    new_job = Job(
        kind=old_job.kind,
        episode_id=old_job.episode_id,
        steps=list(old_job.steps),
        force=old_job.force,
        status="queued",
        message="Queued",
    )
    session.add(new_job)
    session.commit()
    session.refresh(new_job)
    assert new_job.id is not None
    worker.enqueue(new_job.id)
    return job_to_out(session, new_job)


_FINISHED_STATUSES = ("done", "failed", "cancelled")


@router.delete("/jobs", response_model=dict[str, int])
def clear_finished_jobs(
    session: SessionDep,
    status: Annotated[str, Query(description="comma list of finished statuses")] = (
        "done,failed,cancelled"
    ),
) -> dict[str, int]:
    """Delete finished job records (history only; episodes and their data are untouched)."""
    statuses = [s.strip() for s in status.split(",") if s.strip() in _FINISHED_STATUSES]
    if not statuses:
        raise HTTPException(
            status_code=422, detail="Only done, failed or cancelled jobs can be cleared"
        )
    jobs = session.exec(select(Job).where(col(Job.status).in_(statuses))).all()
    for job in jobs:
        session.delete(job)
    session.commit()
    return {"deleted": len(jobs)}


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, session: SessionDep) -> None:
    """Delete one finished job record. Active jobs must be cancelled first."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Cancel the job before deleting it")
    session.delete(job)
    session.commit()
