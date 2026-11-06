"""Podcast artwork: downloaded once next to the podcast's episodes, and the home
page's duotone poster made from it locally (no model calls)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.config import get_settings
from app.models import Podcast

log = logging.getLogger(__name__)

# Home page poster colours: shadows in deep slate, highlights in marigold.
POSTER_DARK = "#1d2638"
POSTER_LIGHT = "#f4b33e"
POSTER_PX = 480


def artwork_path(podcast: Podcast) -> Path | None:
    """The podcast's own artwork on disk, downloading it the first time."""
    s = get_settings()
    if not podcast.image_url or s.download_mode == "fake":
        return None
    dst = s.podcasts_dir / podcast.slug / "artwork.img"
    if dst.is_file():
        return dst
    try:
        resp = httpx.get(podcast.image_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(resp.content)
        return dst
    except httpx.HTTPError:
        log.warning("could not download artwork for %s", podcast.title)
        return None


def poster_path(podcast: Podcast) -> Path | None:
    """A square duotone of the artwork in the home palette, cached beside it."""
    src = artwork_path(podcast)
    if src is None:
        return None
    key = f"{POSTER_DARK}-{POSTER_LIGHT}".replace("#", "")
    dst = src.parent / f"poster-{key}.png"
    if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    from app.books.art import duotone

    try:
        return duotone(src, dst, POSTER_DARK, POSTER_LIGHT, (POSTER_PX, POSTER_PX))
    except (OSError, ValueError) as exc:  # unreadable or unsupported image
        log.warning("could not make a poster for %s: %s", podcast.title, exc)
        return None
