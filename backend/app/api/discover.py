"""Podcast discovery through the Apple Podcasts directory."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app.schemas import DiscoverGenre, DiscoverPodcast
from app.services import discover

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/discover/genres", response_model=list[DiscoverGenre])
def genres() -> list[DiscoverGenre]:
    return discover.GENRES


@router.get("/discover/search", response_model=list[DiscoverPodcast])
def search(
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[DiscoverPodcast]:
    try:
        return discover.search(session, q, limit)
    except discover.DirectoryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/discover/top", response_model=list[DiscoverPodcast])
def top(
    session: SessionDep,
    genre_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
) -> list[DiscoverPodcast]:
    try:
        return discover.top(session, genre_id, limit)
    except discover.DirectoryUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
