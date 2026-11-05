"""RSS/Atom feed parsing and podcast synchronization."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from sqlmodel import Session, select

from app import db, storage
from app.models import Episode, Podcast, utcnow

_BLOCK_TAGS = frozenset(
    {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)
_SKIP_TAGS = frozenset({"script", "style"})
_AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".opus")


@dataclass
class ParsedEpisode:
    """Normalized episode entry parsed from an RSS/Atom feed."""

    guid: str
    number: int
    title: str
    slug: str
    description: str
    published: datetime | None
    audio_url: str
    duration_seconds: int | None


@dataclass
class ParsedFeed:
    """Normalized podcast metadata and episodes parsed from an RSS/Atom feed."""

    title: str
    description: str
    image_url: str | None
    episodes: list[ParsedEpisode]


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip_depth += 1
        elif t in _BLOCK_TAGS:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif t in _BLOCK_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


def strip_html(raw: str | None) -> str:
    """Convert an HTML fragment into clean plain text."""
    if not raw:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(raw)
    stripper.close()
    return stripper.text()


def parse_duration(raw: str | int | float | None) -> int | None:
    """Parse iTunes duration ('HH:MM:SS', 'MM:SS', or seconds) into seconds."""
    if raw is None:
        return None
    if isinstance(raw, int | float):
        val = int(raw)
        return val if val >= 0 else None
    text = str(raw).strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        if len(parts) not in (2, 3):
            return None
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if any(n < 0 for n in nums):
            return None
        if len(nums) == 3:
            return int(nums[0] * 3600 + nums[1] * 60 + nums[2])
        return int(nums[0] * 60 + nums[1])
    try:
        val = int(float(text))
    except ValueError:
        return None
    return val if val >= 0 else None


def _validate_http_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Feed URL must be a valid http(s) URL: {url!r}")
    return cleaned


def _fetch_feed_xml(rss_url: str) -> str:
    url = _validate_http_url(rss_url)
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to fetch feed from {url}: {exc}") from exc
    return resp.text


def _extract_audio_url(entry: Any) -> str | None:
    for link in entry.get("links") or []:
        link_type = str(link.get("type") or "").lower()
        href = link.get("href")
        if "audio" in link_type and href:
            return str(href).strip()
    for enc in entry.get("enclosures") or []:
        enc_type = str(enc.get("type") or "").lower()
        href = enc.get("href") or enc.get("url")
        if not href:
            continue
        href_str = str(href).strip()
        path_lower = href_str.lower().split("?", 1)[0]
        if "audio" in enc_type or path_lower.endswith(_AUDIO_EXTS):
            return href_str
    return None


def _parse_published(entry: Any) -> datetime | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw or not isinstance(raw, str):
            continue
        for parser in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                dt = parser(raw.strip())
                return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
            except (TypeError, ValueError):
                continue
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st is not None:
            try:
                return datetime.fromtimestamp(calendar.timegm(st), tz=UTC)
            except (OverflowError, TypeError, ValueError):
                continue
    return None


def _extract_image_url(feed_meta: Any) -> str | None:
    image = feed_meta.get("image")
    if isinstance(image, dict):
        href = image.get("href") or image.get("url")
        if href:
            return str(href).strip()
    itunes_image = feed_meta.get("itunes_image")
    if isinstance(itunes_image, dict) and itunes_image.get("href"):
        return str(itunes_image["href"]).strip()
    if isinstance(itunes_image, str) and itunes_image.strip():
        return itunes_image.strip()
    return None


def parse_feed(xml_or_url: str) -> ParsedFeed:
    """Parse RSS/Atom XML text (or an HTTP(S) feed URL) into a ParsedFeed."""
    source = xml_or_url.strip()
    if not source:
        raise ValueError("Feed content is empty")
    if source.startswith(("http://", "https://")):
        xml_text = _fetch_feed_xml(source)
    else:
        if "://" in source[:16] and not source.startswith("<"):
            raise ValueError(f"Unsupported feed URL scheme: {source!r}")
        xml_text = xml_or_url

    if "<!entity" in xml_text.lower():
        raise ValueError("XML entity declarations are not permitted in feeds")

    parsed = feedparser.parse(xml_text.encode("utf-8"))
    feed_meta = parsed.feed
    if not parsed.version and not (feed_meta.get("title") and parsed.entries):
        raise ValueError("Input is not a valid RSS or Atom feed")

    feed_title = strip_html(str(feed_meta.get("title") or "")) or "Untitled Podcast"
    raw_feed_desc = (
        feed_meta.get("summary") or feed_meta.get("subtitle") or feed_meta.get("description") or ""
    )
    feed_description = strip_html(str(raw_feed_desc))
    image_url = _extract_image_url(feed_meta)

    raw_items: list[dict[str, Any]] = []
    seen_guids: set[str] = set()
    for entry in parsed.entries:
        audio_url = _extract_audio_url(entry)
        if not audio_url:
            continue
        guid = str(entry.get("id") or entry.get("guid") or audio_url).strip()
        if not guid or guid in seen_guids:
            continue
        seen_guids.add(guid)
        title = strip_html(str(entry.get("title") or "")) or "Untitled Episode"
        raw_desc = entry.get("summary") or entry.get("description") or ""
        raw_items.append(
            {
                "guid": guid,
                "title": title,
                "description": strip_html(str(raw_desc)),
                "published": _parse_published(entry),
                "audio_url": audio_url,
                "duration_seconds": parse_duration(entry.get("itunes_duration")),
            }
        )

    total = len(raw_items)
    episodes: list[ParsedEpisode] = []
    for idx, item in enumerate(raw_items):
        number = total - idx
        episodes.append(
            ParsedEpisode(
                guid=item["guid"],
                number=number,
                title=item["title"],
                slug=storage.episode_slug(number, item["title"]),
                description=item["description"],
                published=item["published"],
                audio_url=item["audio_url"],
                duration_seconds=item["duration_seconds"],
            )
        )

    return ParsedFeed(
        title=feed_title,
        description=feed_description,
        image_url=image_url,
        episodes=episodes,
    )


def _unique_podcast_slug(session: Session, title: str) -> str:
    base = storage.slugify(title)
    existing = set(session.exec(select(Podcast.slug)).all())
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _has_local_artifacts(ep: Episode) -> bool:
    return any(
        (
            ep.downloaded_at is not None,
            ep.transcribed_at is not None,
            ep.summarized_at is not None,
            ep.audio_path is not None,
            ep.transcript_path is not None,
            ep.summary_path is not None,
        )
    )


def sync_podcast(rss_url: str) -> Podcast:
    """Fetch an RSS feed and create or refresh its Podcast and Episode rows."""
    clean_url = _validate_http_url(rss_url)
    xml_text = _fetch_feed_xml(clean_url)
    parsed = parse_feed(xml_text)

    with db.session_scope() as session:
        podcast = session.exec(select(Podcast).where(Podcast.rss_url == clean_url)).first()
        if podcast is None:
            podcast = Podcast(
                title=parsed.title,
                rss_url=clean_url,
                slug=_unique_podcast_slug(session, parsed.title),
                description=parsed.description,
                image_url=parsed.image_url,
                refreshed_at=utcnow(),
            )
            session.add(podcast)
            session.flush()
        else:
            podcast.title = parsed.title
            podcast.description = parsed.description
            podcast.image_url = parsed.image_url
            podcast.refreshed_at = utcnow()
            session.add(podcast)

        assert podcast.id is not None
        existing_eps = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
        by_guid = {ep.guid: ep for ep in existing_eps}

        for pe in parsed.episodes:
            ep = by_guid.get(pe.guid)
            if ep is None:
                session.add(
                    Episode(
                        podcast_id=podcast.id,
                        guid=pe.guid,
                        number=pe.number,
                        title=pe.title,
                        slug=pe.slug,
                        description=pe.description,
                        published=pe.published,
                        audio_url=pe.audio_url,
                        duration_seconds=pe.duration_seconds,
                    )
                )
            else:
                ep.title = pe.title
                ep.description = pe.description
                ep.published = pe.published
                ep.audio_url = pe.audio_url
                ep.duration_seconds = pe.duration_seconds
                ep.number = pe.number
                if not _has_local_artifacts(ep):
                    ep.slug = pe.slug
                session.add(ep)

        session.commit()
        session.refresh(podcast)
        return podcast
