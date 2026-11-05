"""In-process asyncio job queue and worker pool for podcast ingestion."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import cast

from sqlmodel import Session, col, select

from app import db
from app.config import get_settings
from app.domain import ProgressFn
from app.models import Episode, Job, utcnow
from app.schemas import JobKind, JobOut, JobStatus, SelectionRequest, Step
from app.services.downloader import download_episode
from app.services.transcribe import transcribe_episode

_CANONICAL_STEPS: tuple[Step, ...] = ("download", "transcribe", "index")
_ACTIVE_STATUSES: tuple[str, ...] = ("queued", "running")
_PROGRESS_MIN_INTERVAL = 1.0  # seconds (<= 1 write/s)


class JobCancelled(Exception):
    """Raised inside a worker step when its job has been cancelled."""


def matches_episode_query(
    episode: Episode,
    q: str | None,
    search_description: bool = False,
) -> bool:
    """Return True if any whitespace-separated keyword matches title/description."""
    if not q or not q.strip():
        return True
    keywords = [kw.lower() for kw in q.split() if kw.strip()]
    if not keywords:
        return True
    haystack = episode.title.lower()
    if search_description and episode.description:
        haystack = f"{haystack} {episode.description.lower()}"
    return any(kw in haystack for kw in keywords)


def episode_needs_step(episode: Episode, step: Step, *, force: bool = False) -> bool:
    """Return True if the episode still requires the given pipeline step."""
    if force:
        return True
    if step == "download":
        return episode.downloaded_at is None
    if step == "transcribe":
        return episode.transcribed_at is None
    return step == "index" and episode.indexed_at is None


def resolve_selection(session: Session, sel: SelectionRequest) -> list[Episode]:
    """Resolve a SelectionRequest (explicit IDs or filter) into Episode rows."""
    if sel.episode_ids is not None:
        if not sel.episode_ids:
            return []
        stmt = (
            select(Episode)
            .where(col(Episode.id).in_(sel.episode_ids))
            .order_by(
                col(Episode.published).desc(),
                col(Episode.number).desc(),
                col(Episode.id).desc(),
            )
        )
        rows = list(session.exec(stmt).all())
        if sel.podcast_id is not None:
            rows = [ep for ep in rows if ep.podcast_id == sel.podcast_id]
        if sel.q:
            rows = [ep for ep in rows if matches_episode_query(ep, sel.q, sel.search_description)]
        return rows

    stmt = select(Episode)
    if sel.podcast_id is not None:
        stmt = stmt.where(Episode.podcast_id == sel.podcast_id)
    stmt = stmt.order_by(
        col(Episode.published).desc(),
        col(Episode.number).desc(),
        col(Episode.id).desc(),
    )
    rows = list(session.exec(stmt).all())
    if sel.q:
        rows = [ep for ep in rows if matches_episode_query(ep, sel.q, sel.search_description)]
    if sel.status is not None:
        from app.api.episodes import episode_status

        rows = [ep for ep in rows if episode_status(ep) == sel.status]
    return rows


def job_to_out(session: Session, job: Job) -> JobOut:
    """Serialize a Job ORM model into the API JobOut schema."""
    assert job.id is not None
    ep_title: str | None = None
    if job.episode_id is not None:
        ep = session.get(Episode, job.episode_id)
        if ep is not None:
            ep_title = ep.title
    valid_steps: list[Step] = [cast(Step, s) for s in job.steps if s in _CANONICAL_STEPS]
    return JobOut(
        id=job.id,
        kind=cast(JobKind, job.kind),
        episode_id=job.episode_id,
        episode_title=ep_title,
        steps=valid_steps,
        status=cast(JobStatus, job.status),
        current_step=job.current_step,
        progress=job.progress,
        message=job.message,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


class JobWorker:
    """Asyncio background worker executing queued ingestion/RAG jobs."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[int | None] | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._lock = threading.Lock()
        self._cancelled: set[int] = set()

    async def start(self) -> None:
        """Start worker tasks and re-queue jobs left queued/running in SQLite."""
        loop = asyncio.get_running_loop()
        if self._running and self._loop is loop:
            return

        self._loop = loop
        self._queue = asyncio.Queue()
        with self._lock:
            self._cancelled.clear()
        self._running = True

        pending_ids: list[int] = []
        with db.session_scope() as session:
            stale_jobs = session.exec(
                select(Job)
                .where(col(Job.status).in_(_ACTIVE_STATUSES))
                .order_by(col(Job.created_at).asc(), col(Job.id).asc())
            ).all()
            for job in stale_jobs:
                if job.id is None:
                    continue
                if job.status == "running":
                    job.status = "queued"
                    job.current_step = None
                    job.progress = 0.0
                    job.message = "Re-queued on startup"
                    session.add(job)
                pending_ids.append(job.id)
            session.commit()

        for job_id in pending_ids:
            self._queue.put_nowait(job_id)

        concurrency = max(1, get_settings().job_concurrency)
        self._tasks = [
            asyncio.create_task(self._worker_loop(), name=f"job-worker-{i}")
            for i in range(concurrency)
        ]

    async def stop(self) -> None:
        """Gracefully stop worker tasks."""
        if not self._running and not self._tasks:
            return
        self._running = False
        if self._queue is not None:
            for _ in self._tasks:
                self._queue.put_nowait(None)
        if self._tasks:
            _done, pending = await asyncio.wait(self._tasks, timeout=5.0)
            for task in pending:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._loop = None

    async def wait_for_idle(self, timeout: float = 10.0) -> None:
        """Wait until all currently queued jobs finish processing."""
        if self._queue is not None:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)

    def enqueue(self, job_id: int) -> None:
        """Schedule a persisted job ID for execution (safe from any thread)."""
        loop = self._loop
        queue = self._queue
        if not self._running or loop is None or queue is None or loop.is_closed():
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            queue.put_nowait(job_id)
        else:
            loop.call_soon_threadsafe(queue.put_nowait, job_id)

    def cancel(self, job_id: int) -> Job | None:
        """Mark a queued or running job as cancelled."""
        with self._lock:
            self._cancelled.add(job_id)
        with db.session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            if job.status in _ACTIVE_STATUSES:
                job.status = "cancelled"
                job.current_step = None
                job.message = "Cancelled"
                job.finished_at = utcnow()
                session.add(job)
                session.commit()
                session.refresh(job)
            return job

    def _is_cancelled_fast(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._cancelled

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            job_id = await queue.get()
            try:
                if job_id is None:
                    return
                await self._process_job(job_id)
            finally:
                queue.task_done()

    async def _process_job(self, job_id: int) -> None:
        if self._is_cancelled_fast(job_id):
            with db.session_scope() as session:
                job = session.get(Job, job_id)
                if job is not None and job.status in _ACTIVE_STATUSES:
                    job.status = "cancelled"
                    job.current_step = None
                    job.message = "Cancelled"
                    job.finished_at = utcnow()
                    session.add(job)
                    session.commit()
            return

        with db.session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status not in _ACTIVE_STATUSES:
                return
            job.status = "running"
            job.started_at = utcnow()
            job.error = None
            job.progress = 0.0
            job.message = "Starting"
            session.add(job)
            session.commit()
            kind = job.kind
            episode_id = job.episode_id
            steps = list(job.steps)
            force = job.force

        try:
            await asyncio.to_thread(
                self._execute_job_sync,
                job_id,
                kind,
                episode_id,
                steps,
                force,
            )
        except JobCancelled:
            with db.session_scope() as session:
                job = session.get(Job, job_id)
                if job is not None:
                    job.status = "cancelled"
                    job.current_step = None
                    job.message = "Cancelled"
                    job.finished_at = utcnow()
                    session.add(job)
                    session.commit()
            return
        except Exception as exc:
            err_text = str(exc).strip() or exc.__class__.__name__
            with db.session_scope() as session:
                job = session.get(Job, job_id)
                if job is not None:
                    if job.status == "cancelled" or self._is_cancelled_fast(job_id):
                        job.status = "cancelled"
                        job.message = "Cancelled"
                    else:
                        job.status = "failed"
                        job.error = err_text
                        job.message = "Failed"
                    job.current_step = None
                    job.finished_at = utcnow()
                    session.add(job)
                    session.commit()
            return

        with db.session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            if job.status == "cancelled" or self._is_cancelled_fast(job_id):
                job.status = "cancelled"
                job.current_step = None
                job.message = "Cancelled"
                job.finished_at = utcnow()
            else:
                job.status = "done"
                job.current_step = None
                job.progress = 1.0
                job.message = "Completed"
                job.finished_at = utcnow()
            session.add(job)
            session.commit()

    def _make_progress_cb(self, job_id: int, step_name: str) -> ProgressFn:
        last_write = 0.0

        def _on_progress(fraction: float, message: str) -> None:
            nonlocal last_write
            if self._is_cancelled_fast(job_id):
                raise JobCancelled("Job was cancelled")

            now = time.monotonic()
            with db.session_scope() as session:
                job = session.get(Job, job_id)
                if job is None or job.status == "cancelled":
                    with self._lock:
                        self._cancelled.add(job_id)
                    raise JobCancelled("Job was cancelled")
                if now - last_write >= _PROGRESS_MIN_INTERVAL:
                    job.current_step = step_name
                    job.progress = max(0.0, min(1.0, float(fraction)))
                    job.message = message
                    session.add(job)
                    session.commit()
                    last_write = now

        return _on_progress

    def _begin_step(self, job_id: int, step_name: str) -> ProgressFn:
        if self._is_cancelled_fast(job_id):
            raise JobCancelled("Job was cancelled")
        with db.session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status == "cancelled":
                with self._lock:
                    self._cancelled.add(job_id)
                raise JobCancelled("Job was cancelled")
            job.current_step = step_name
            job.progress = 0.0
            job.message = f"Running {step_name}"
            session.add(job)
            session.commit()
        return self._make_progress_cb(job_id, step_name)

    def _execute_job_sync(
        self,
        job_id: int,
        kind: str,
        episode_id: int | None,
        steps: list[str],
        force: bool,
    ) -> None:
        if kind == "process":
            if episode_id is None:
                raise ValueError("process job requires episode_id")
            ordered = [s for s in _CANONICAL_STEPS if s in steps]
            for step in ordered:
                cb = self._begin_step(job_id, step)
                if step == "download":
                    download_episode(episode_id, on_progress=cb, force=force)
                elif step == "transcribe":
                    transcribe_episode(episode_id, on_progress=cb, force=force)
                elif step == "index":
                    from app.services import indexing

                    indexing.index_episode(episode_id, on_progress=cb, force=force)
        elif kind == "summarize":
            if episode_id is None:
                raise ValueError("summarize job requires episode_id")
            from app.services import summarize

            cb = self._begin_step(job_id, "summarize")
            summarize.summarize_episode(episode_id, on_progress=cb, force=force)
        elif kind == "reindex":
            if episode_id is None:
                raise ValueError("reindex job requires episode_id")
            from app.services import indexing

            cb = self._begin_step(job_id, "index")
            indexing.index_episode(episode_id, on_progress=cb, force=True)
        elif kind == "rebuild_index":
            from app.services import indexing

            cb = self._begin_step(job_id, "rebuild_index")
            indexing.rebuild_index(on_progress=cb)
        else:
            raise ValueError(f"Unknown job kind: {kind!r}")


worker = JobWorker()


def create_jobs(sel: SelectionRequest) -> list[Job]:
    """Create and enqueue process jobs for episodes needing requested steps."""
    ordered_steps: list[Step] = [s for s in _CANONICAL_STEPS if s in sel.steps]
    if not ordered_steps:
        return []

    created: list[Job] = []
    with db.session_scope() as session:
        episodes = resolve_selection(session, sel)
        if not episodes:
            return []

        active_ep_ids = {
            ep_id
            for ep_id in session.exec(
                select(Job.episode_id).where(
                    col(Job.status).in_(_ACTIVE_STATUSES),
                    col(Job.episode_id).is_not(None),
                )
            ).all()
            if ep_id is not None
        }

        for ep in episodes:
            if ep.id is None or ep.id in active_ep_ids:
                continue
            needed = [
                step for step in ordered_steps if episode_needs_step(ep, step, force=sel.force)
            ]
            if not sel.force and not needed:
                continue
            job = Job(
                kind="process",
                episode_id=ep.id,
                steps=list(ordered_steps),
                force=sel.force,
                status="queued",
                message="Queued",
            )
            session.add(job)
            created.append(job)
            active_ep_ids.add(ep.id)

        session.commit()
        for job in created:
            session.refresh(job)

    for job in created:
        if job.id is not None:
            worker.enqueue(job.id)

    return created
