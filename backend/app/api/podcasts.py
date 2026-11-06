"""Podcast feed CRUD and refresh endpoints."""

import shutil
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.jobs.worker import worker
from app.models import Episode, Job, Podcast
from app.schemas import PodcastCreate, PodcastOut
from app.services.artwork import poster_path
from app.services.feeds import sync_podcast

# TODO(security): Add authentication, CSRF protection, and rate limiting at the API gateway
# or FastAPI middleware layer if this local single-user service is ever exposed beyond localhost.

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


def _remove_episode_vectors(episode_id: int) -> None:
    try:
        from app.services import indexing

        indexing.remove_episode(episode_id)
    except ImportError:
        with suppress(ImportError):
            from app.services.vectorstore import get_vector_store

            get_vector_store().delete_episode(episode_id)


def _podcast_to_out(session: Session, podcast: Podcast) -> PodcastOut:
    assert podcast.id is not None
    total = session.exec(
        select(func.count()).select_from(Episode).where(Episode.podcast_id == podcast.id)
    ).one()
    indexed = session.exec(
        select(func.count())
        .select_from(Episode)
        .where(
            Episode.podcast_id == podcast.id,
            col(Episode.indexed_at).is_not(None),
        )
    ).one()
    return PodcastOut(
        id=podcast.id,
        title=podcast.title,
        rss_url=podcast.rss_url,
        description=podcast.description,
        image_url=podcast.image_url,
        episode_count=int(total),
        indexed_count=int(indexed),
        refreshed_at=podcast.refreshed_at,
    )


@router.get("/podcasts/{podcast_id}/poster.png")
async def podcast_poster(podcast_id: int, session: SessionDep) -> FileResponse:
    """The show's artwork as a duotone poster for the home page (made locally, cached).
    404 when the show has no artwork; the page then draws a typographic poster."""
    podcast = session.get(Podcast, podcast_id)
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")
    path = await run_in_threadpool(poster_path, podcast)
    if path is None:
        raise HTTPException(status_code=404, detail="This podcast has no artwork")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.get("/podcasts", response_model=list[PodcastOut])
def list_podcasts(session: SessionDep) -> list[PodcastOut]:
    """List tracked podcasts without performing any network calls."""
    podcasts = session.exec(select(Podcast).order_by(col(Podcast.id).asc())).all()
    return [_podcast_to_out(session, p) for p in podcasts]


@router.post("/podcasts", response_model=PodcastOut, status_code=201)
def add_podcast(body: PodcastCreate, session: SessionDep) -> PodcastOut:
    """Add a new podcast by RSS URL and import its episode catalog."""
    rss_url = body.rss_url.strip()
    if not rss_url:
        raise HTTPException(status_code=422, detail="rss_url must not be empty")

    existing = session.exec(select(Podcast).where(Podcast.rss_url == rss_url)).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Podcast with this RSS URL already exists",
        )

    try:
        synced = sync_podcast(rss_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.expire_all()
    podcast = session.get(Podcast, synced.id)
    assert podcast is not None
    return _podcast_to_out(session, podcast)


@router.post("/podcasts/{podcast_id}/refresh", response_model=PodcastOut)
def refresh_podcast(podcast_id: int, session: SessionDep) -> PodcastOut:
    """Re-fetch a podcast's RSS feed and upsert episodes."""
    podcast = session.get(Podcast, podcast_id)
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")

    try:
        sync_podcast(podcast.rss_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.expire_all()
    refreshed = session.get(Podcast, podcast_id)
    assert refreshed is not None
    return _podcast_to_out(session, refreshed)


@router.delete("/podcasts/{podcast_id}", status_code=204)
def delete_podcast(
    podcast_id: int,
    session: SessionDep,
    delete_files: bool = True,
) -> Response:
    """Delete a podcast, its episodes, vectors, jobs, and optionally local files."""
    podcast = session.get(Podcast, podcast_id)
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")

    podcast_slug = podcast.slug
    ep_ids = [
        ep.id
        for ep in session.exec(select(Episode).where(Episode.podcast_id == podcast_id)).all()
        if ep.id is not None
    ]

    if ep_ids:
        jobs = session.exec(select(Job).where(col(Job.episode_id).in_(ep_ids))).all()
        for job in jobs:
            if job.id is not None and job.status in ("queued", "running"):
                worker.cancel(job.id)
        for ep_id in ep_ids:
            _remove_episode_vectors(ep_id)

    session.expire_all()
    if ep_ids:
        for job in session.exec(select(Job).where(col(Job.episode_id).in_(ep_ids))).all():
            session.delete(job)
        session.flush()
        for ep in session.exec(select(Episode).where(Episode.podcast_id == podcast_id)).all():
            session.delete(ep)
        session.flush()

    target_podcast = session.get(Podcast, podcast_id)
    if target_podcast is not None:
        session.delete(target_podcast)
    session.commit()

    if delete_files:
        podcasts_root = get_settings().podcasts_dir.resolve()
        podcast_dir = (podcasts_root / podcast_slug).resolve()
        if podcast_dir != podcasts_root and podcast_dir.is_relative_to(podcasts_root):
            shutil.rmtree(podcast_dir, ignore_errors=True)

    return Response(status_code=204)
