"""Episode catalog, audio streaming, cost estimation, and pipeline action endpoints."""

import shutil
from contextlib import suppress
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app import storage
from app.config import get_settings
from app.db import get_session
from app.jobs.worker import create_jobs, job_to_out, matches_episode_query, worker
from app.models import Conversation, Episode, Job, Message, Podcast
from app.schemas import (
    CostEstimate,
    EpisodeCitationRef,
    EpisodeDetail,
    EpisodeList,
    EpisodeOut,
    EpisodeStatus,
    JobOut,
    SegmentOut,
    SelectionRequest,
    TranscriptCheck,
)
from app.services.estimate import estimate

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
_ACTIVE_JOB_STATUSES = ("queued", "running")


def episode_status(episode: Episode) -> EpisodeStatus:
    """Return the furthest completed pipeline stage for an episode."""
    if episode.indexed_at is not None:
        return "indexed"
    if episode.transcribed_at is not None:
        return "transcribed"
    if episode.downloaded_at is not None:
        return "downloaded"
    return "new"


def _safe_data_path(rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    data_root = get_settings().data_dir.resolve()
    candidate = storage.to_abs(rel_path).resolve()
    if candidate != data_root and candidate.is_relative_to(data_root):
        return candidate
    return None


def _has_summary(episode: Episode) -> bool:
    if episode.summarized_at is not None:
        return True
    sp = _safe_data_path(episode.summary_path)
    return bool(sp is not None and sp.is_file())


def _episode_to_out(
    episode: Episode,
    podcast_title: str,
    active_job_id: int | None,
) -> EpisodeOut:
    assert episode.id is not None
    return EpisodeOut(
        id=episode.id,
        podcast_id=episode.podcast_id,
        podcast_title=podcast_title,
        number=episode.number,
        title=episode.title,
        description=episode.description,
        published=episode.published,
        duration_seconds=episode.duration_seconds,
        status=episode_status(episode),
        has_summary=_has_summary(episode),
        speakers=dict(episode.speakers or {}),
        passage_count=episode.passage_count,
        active_job_id=active_job_id,
    )


def _active_jobs_by_episode(session: Session) -> dict[int, int]:
    jobs = session.exec(
        select(Job)
        .where(
            col(Job.status).in_(_ACTIVE_JOB_STATUSES),
            col(Job.episode_id).is_not(None),
        )
        .order_by(col(Job.id).desc())
    ).all()
    mapping: dict[int, int] = {}
    for job in jobs:
        if job.episode_id is not None and job.id is not None:
            mapping.setdefault(job.episode_id, job.id)
    return mapping


def _remove_episode_vectors(episode_id: int) -> None:
    try:
        from app.services import indexing

        indexing.remove_episode(episode_id)
    except ImportError:
        with suppress(ImportError):
            from app.services.vectorstore import get_vector_store

            get_vector_store().delete_episode(episode_id)


@router.get("/episodes", response_model=EpisodeList)
def list_episodes(
    session: SessionDep,
    podcast_id: int | None = None,
    q: str | None = None,
    search_description: bool = False,
    status: EpisodeStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EpisodeList:
    """List episodes newest first with keyword, podcast, and status filters."""
    stmt = select(Episode)
    if podcast_id is not None:
        stmt = stmt.where(Episode.podcast_id == podcast_id)
    stmt = stmt.order_by(
        col(Episode.published).desc(),
        col(Episode.number).desc(),
        col(Episode.id).desc(),
    )
    rows = list(session.exec(stmt).all())

    if q:
        rows = [ep for ep in rows if matches_episode_query(ep, q, search_description)]
    if status is not None:
        rows = [ep for ep in rows if episode_status(ep) == status]

    total = len(rows)
    page = rows[offset : offset + limit]

    podcast_titles = {
        p.id: p.title for p in session.exec(select(Podcast)).all() if p.id is not None
    }
    active_jobs = _active_jobs_by_episode(session)

    items = [
        _episode_to_out(
            ep,
            podcast_titles.get(ep.podcast_id, ""),
            active_jobs.get(ep.id) if ep.id is not None else None,
        )
        for ep in page
    ]
    return EpisodeList(items=items, total=total)


@router.post("/episodes/estimate", response_model=CostEstimate)
def estimate_episodes(sel: SelectionRequest) -> CostEstimate:
    """Estimate processing cost for a selection of episodes."""
    return estimate(sel)


@router.post("/episodes/process", response_model=list[JobOut])
def process_episodes(sel: SelectionRequest, session: SessionDep) -> list[JobOut]:
    """Create and enqueue processing jobs for selected episodes."""
    jobs = create_jobs(sel)
    session.expire_all()
    out: list[JobOut] = []
    for job in jobs:
        if job.id is None:
            continue
        fresh = session.get(Job, job.id) or job
        out.append(job_to_out(session, fresh))
    return out


@router.get("/episodes/{episode_id}", response_model=EpisodeDetail)
def get_episode(episode_id: int, session: SessionDep) -> EpisodeDetail:
    """Return full episode metadata, transcript segments, and optional summary."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    podcast = session.get(Podcast, episode.podcast_id)
    podcast_title = podcast.title if podcast is not None else ""
    active_job = session.exec(
        select(Job)
        .where(
            Job.episode_id == episode_id,
            col(Job.status).in_(_ACTIVE_JOB_STATUSES),
        )
        .order_by(col(Job.id).desc())
    ).first()
    active_job_id = active_job.id if active_job is not None else None

    audio_file = _safe_data_path(episode.audio_path)
    local_audio = bool(audio_file is not None and audio_file.is_file())

    segments: list[SegmentOut] = []
    transcript_file = _safe_data_path(episode.transcript_path)
    if transcript_file is not None and transcript_file.is_file():
        transcript = storage.read_transcript(transcript_file)
        segments = [
            SegmentOut(
                speaker=seg.speaker,
                start=seg.start,
                end=seg.end,
                text=seg.text,
            )
            for seg in transcript.segments
        ]

    summary_markdown: str | None = None
    summary_file = _safe_data_path(episode.summary_path)
    if summary_file is not None and summary_file.is_file():
        summary_markdown = summary_file.read_text("utf-8")

    base = _episode_to_out(episode, podcast_title, active_job_id)
    return EpisodeDetail(
        **base.model_dump(),
        audio_url=episode.audio_url,
        local_audio=local_audio,
        downloaded_at=episode.downloaded_at,
        transcribed_at=episode.transcribed_at,
        indexed_at=episode.indexed_at,
        summarized_at=episode.summarized_at,
        transcript_check=episode.transcript_check,
        segments=segments,
        summary_markdown=summary_markdown,
    )


@router.get("/episodes/{episode_id}/audio")
def get_episode_audio(episode_id: int, session: SessionDep) -> FileResponse:
    """Serve the locally downloaded MP3 file with HTTP Range support."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    audio_file = _safe_data_path(episode.audio_path)
    if audio_file is None or not audio_file.is_file():
        raise HTTPException(status_code=404, detail="Local audio file not found")
    return FileResponse(
        path=audio_file,
        media_type="audio/mpeg",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/episodes/{episode_id}/summarize", response_model=JobOut)
def summarize_episode_endpoint(
    episode_id: int,
    session: SessionDep,
    force: bool = False,
) -> JobOut:
    """Enqueue a summary generation job for an episode."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    existing = session.exec(
        select(Job).where(
            Job.episode_id == episode_id,
            Job.kind == "summarize",
            col(Job.status).in_(_ACTIVE_JOB_STATUSES),
        )
    ).first()
    if existing is not None:
        return job_to_out(session, existing)

    job = Job(
        kind="summarize",
        episode_id=episode_id,
        steps=[],
        force=force,
        status="queued",
        message="Queued",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.id is not None
    worker.enqueue(job.id)
    return job_to_out(session, job)


@router.post("/episodes/{episode_id}/check", response_model=TranscriptCheck)
async def check_episode(episode_id: int, session: SessionDep) -> TranscriptCheck:
    """Re-run the transcript health check (mechanical checks + speaker-name check)."""
    from fastapi.concurrency import run_in_threadpool

    from app.services.transcript_check import run_check

    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.transcript_path:
        raise HTTPException(status_code=409, detail="This episode has no transcript yet")
    result = await run_in_threadpool(run_check, episode_id)
    return TranscriptCheck.model_validate(result)


@router.post("/episodes/{episode_id}/reindex", response_model=JobOut)
def reindex_episode_endpoint(episode_id: int, session: SessionDep) -> JobOut:
    """Enqueue a force re-index job for an episode."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    existing = session.exec(
        select(Job).where(
            Job.episode_id == episode_id,
            Job.kind == "reindex",
            col(Job.status).in_(_ACTIVE_JOB_STATUSES),
        )
    ).first()
    if existing is not None:
        return job_to_out(session, existing)

    job = Job(
        kind="reindex",
        episode_id=episode_id,
        steps=["index"],
        force=True,
        status="queued",
        message="Queued",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.id is not None
    worker.enqueue(job.id)
    return job_to_out(session, job)


@router.delete("/episodes/{episode_id}/data", status_code=204)
def delete_episode_data(episode_id: int, session: SessionDep) -> Response:
    """Delete local files and vector embeddings for an episode and reset its state."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    podcast = session.get(Podcast, episode.podcast_id)
    podcast_slug = podcast.slug if podcast is not None else None
    ep_slug = episode.slug
    rel_paths = [episode.audio_path, episode.transcript_path, episode.summary_path]

    active_jobs = session.exec(
        select(Job).where(
            Job.episode_id == episode_id,
            col(Job.status).in_(_ACTIVE_JOB_STATUSES),
        )
    ).all()
    for job in active_jobs:
        if job.id is not None:
            worker.cancel(job.id)

    _remove_episode_vectors(episode_id)

    for rel in rel_paths:
        target = _safe_data_path(rel)
        if target is not None:
            target.unlink(missing_ok=True)
            if target.suffix == ".json":
                target.with_suffix(".md").unlink(missing_ok=True)

    if podcast_slug is not None:
        podcasts_root = get_settings().podcasts_dir.resolve()
        ep_dir = (podcasts_root / podcast_slug / ep_slug).resolve()
        if ep_dir != podcasts_root and ep_dir.is_relative_to(podcasts_root):
            shutil.rmtree(ep_dir, ignore_errors=True)

    session.expire_all()
    ep = session.get(Episode, episode_id)
    if ep is not None:
        ep.audio_path = None
        ep.downloaded_at = None
        ep.transcript_path = None
        ep.transcribed_at = None
        ep.speakers = {}
        ep.indexed_at = None
        ep.passage_count = 0
        ep.summary_path = None
        ep.summarized_at = None
        session.add(ep)
        session.commit()

    return Response(status_code=204)


@router.get("/episodes/{episode_id}/citations", response_model=list[EpisodeCitationRef])
def get_episode_citations(episode_id: int, session: SessionDep) -> list[EpisodeCitationRef]:
    """Every saved answer that cited this episode, oldest first (for transcript back-links)."""
    if session.get(Episode, episode_id) is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    rows = session.exec(
        select(Message, Conversation)
        .join(Conversation, col(Message.conversation_id) == col(Conversation.id))
        .where(Message.role == "assistant")
        .order_by(col(Message.created_at))
    ).all()
    refs: list[EpisodeCitationRef] = []
    for msg, conv in rows:
        for cit in msg.citations or []:
            if cit.get("episode_id") != episode_id or cit.get("source") == "summary":
                continue
            assert msg.id is not None and conv.id is not None
            refs.append(
                EpisodeCitationRef(
                    conversation_id=conv.id,
                    conversation_title=conv.title,
                    message_id=msg.id,
                    n=int(cit.get("n", 0)),
                    start=float(cit.get("start", 0.0)),
                    end=float(cit.get("end", 0.0)),
                    speaker=str(cit.get("speaker", "")),
                    created_at=msg.created_at,
                )
            )
    return refs
