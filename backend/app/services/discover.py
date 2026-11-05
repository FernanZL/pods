"""Find podcasts by name or browse top charts via the free Apple Podcasts directory.

No API key needed. Results include the public RSS feed URL so a podcast can be added
to the library in one step. Chart lookups are cached in memory for an hour.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from sqlmodel import Session, select

from app.models import Podcast
from app.schemas import DiscoverGenre, DiscoverPodcast

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"
CHART_URL = "https://itunes.apple.com/{country}/rss/toppodcasts/limit={limit}{genre}/json"
_TIMEOUT = httpx.Timeout(15.0)
_CHART_TTL = 3600.0
_chart_cache: dict[tuple[str, int | None, int], tuple[float, list[dict[str, Any]]]] = {}

# Apple Podcasts top-level genres (stable ids).
GENRES: list[DiscoverGenre] = [
    DiscoverGenre(id=1533, name="Science"),
    DiscoverGenre(id=1512, name="Health & Fitness"),
    DiscoverGenre(id=1304, name="Education"),
    DiscoverGenre(id=1318, name="Technology"),
    DiscoverGenre(id=1321, name="Business"),
    DiscoverGenre(id=1324, name="Society & Culture"),
    DiscoverGenre(id=1489, name="News"),
    DiscoverGenre(id=1487, name="History"),
    DiscoverGenre(id=1488, name="True Crime"),
    DiscoverGenre(id=1303, name="Comedy"),
    DiscoverGenre(id=1309, name="TV & Film"),
    DiscoverGenre(id=1545, name="Sports"),
]


class DirectoryUnavailable(RuntimeError):
    """The Apple directory could not be reached or returned something unusable."""


def _get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        resp = httpx.get(url, params=params, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DirectoryUnavailable(f"Apple Podcasts directory unavailable: {exc}") from exc


def _to_result(raw: dict[str, Any], known: dict[str, int]) -> DiscoverPodcast | None:
    itunes_id = raw.get("collectionId") or raw.get("trackId")
    title = raw.get("collectionName") or raw.get("trackName")
    if not itunes_id or not title:
        return None
    feed = raw.get("feedUrl")
    return DiscoverPodcast(
        itunes_id=int(itunes_id),
        title=str(title),
        author=str(raw.get("artistName") or ""),
        feed_url=feed,
        artwork_url=raw.get("artworkUrl600") or raw.get("artworkUrl100"),
        genre=raw.get("primaryGenreName"),
        episode_count=raw.get("trackCount"),
        podcast_id=known.get(feed) if feed else None,
    )


def _known_feeds(session: Session) -> dict[str, int]:
    return {p.rss_url: p.id for p in session.exec(select(Podcast)).all() if p.id is not None}


def search(session: Session, term: str, limit: int = 20) -> list[DiscoverPodcast]:
    """Search the directory by podcast name (or host)."""
    term = term.strip()
    if not term:
        return []
    data = _get_json(
        SEARCH_URL,
        {"media": "podcast", "entity": "podcast", "term": term, "limit": max(1, min(limit, 50))},
    )
    known = _known_feeds(session)
    results = [_to_result(r, known) for r in data.get("results", [])]
    return [r for r in results if r is not None]


def top(
    session: Session, genre_id: int | None = None, limit: int = 24, country: str = "us"
) -> list[DiscoverPodcast]:
    """Top podcasts overall or within a genre, resolved to feed URLs."""
    limit = max(1, min(limit, 50))
    key = (country, genre_id, limit)
    cached = _chart_cache.get(key)
    if cached and time.monotonic() - cached[0] < _CHART_TTL:
        raw_items = cached[1]
    else:
        chart = _get_json(
            CHART_URL.format(
                country=country,
                limit=limit,
                genre=f"/genre={genre_id}" if genre_id else "",
            )
        )
        entries = chart.get("feed", {}).get("entry", []) or []
        if isinstance(entries, dict):  # a single entry is not wrapped in a list
            entries = [entries]
        ids = [e["id"]["attributes"]["im:id"] for e in entries if e.get("id")]
        if not ids:
            return []
        lookup = _get_json(LOOKUP_URL, {"id": ",".join(ids), "entity": "podcast"})
        by_id = {str(r.get("collectionId")): r for r in lookup.get("results", [])}
        raw_items = [by_id[i] for i in ids if i in by_id]  # keep chart order
        _chart_cache[key] = (time.monotonic(), raw_items)
    known = _known_feeds(session)
    results = [_to_result(r, known) for r in raw_items]
    return [r for r in results if r is not None]
