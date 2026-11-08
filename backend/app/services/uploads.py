"""Audio files uploaded from this computer, as episodes of a local "show".

An upload works like an RSS episode that is already downloaded: it gets a Podcast
row (rss_url ``upload://<slug>``, never refreshed) and an Episode whose audio sits
in the usual episode folder, so transcribe → index → books run unchanged.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from app import db, storage
from app.models import Episode, Podcast, utcnow
from app.services import audio
from app.services.feeds import _unique_podcast_slug

UPLOAD_SCHEME = "upload://"
DEFAULT_SHOW = "My uploads"
AUDIO_SUFFIXES = frozenset(
    {".mp3", ".m4a", ".mp4", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".webm", ".mpga"}
)
MAX_UPLOAD_BYTES = 2 * 1024**3  # 2 GiB: a long episode as WAV still fits


def is_upload(url: str | None) -> bool:
    return bool(url) and str(url).startswith(UPLOAD_SCHEME)


def audio_suffix(filename: str) -> str:
    """The file's audio extension (lower case), or ValueError if it is not audio."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        allowed = ", ".join(sorted(s.lstrip(".") for s in AUDIO_SUFFIXES))
        raise ValueError(f"Unsupported file type {suffix or '(none)'!r}. Use one of: {allowed}")
    return suffix


def staging_dir() -> Path:
    """Where an upload is written while it streams in (same disk as the data dir)."""
    d = storage.to_abs("uploads-tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _show(session: Session, name: str) -> Podcast:
    title = " ".join(name.split()) or DEFAULT_SHOW
    rss_url = UPLOAD_SCHEME + storage.slugify(title)
    podcast = session.exec(select(Podcast).where(Podcast.rss_url == rss_url)).first()
    if podcast is None:
        podcast = Podcast(
            title=title,
            rss_url=rss_url,
            slug=_unique_podcast_slug(session, title),
            description="Audio files uploaded from this computer.",
        )
        session.add(podcast)
        session.flush()
    return podcast


def probe_seconds(path: Path) -> int | None:
    """Duration in whole seconds. None when ffprobe is not installed; ValueError when
    the file cannot be read as audio."""
    try:
        return max(1, round(audio.probe_duration(path)))
    except RuntimeError as exc:
        if "not found on PATH" in str(exc):
            return None
        raise ValueError("This file could not be read as audio") from exc


def add_upload(
    staged: Path,
    *,
    filename: str,
    title: str,
    show: str = "",
    description: str = "",
) -> Episode:
    """Turn a staged file into a downloaded episode. Moves (consumes) `staged`."""
    suffix = audio_suffix(filename)
    duration = probe_seconds(staged)
    clean_title = " ".join(title.split()) or Path(filename).stem.replace("_", " ").strip()
    with db.session_scope() as session:
        podcast = _show(session, show)
        assert podcast.id is not None
        last = session.exec(
            select(func.max(Episode.number)).where(Episode.podcast_id == podcast.id)
        ).one()
        number = int(last or 0) + 1
        episode = Episode(
            podcast_id=podcast.id,
            guid=f"upload:{uuid.uuid4().hex}",
            number=number,
            title=clean_title or f"Upload {number}",
            slug=storage.episode_slug(number, clean_title or "upload"),
            description=description.strip(),
            published=utcnow(),
            audio_url=UPLOAD_SCHEME + storage.sanitize_filename(Path(filename).name),
            duration_seconds=duration,
        )
        session.add(episode)
        session.flush()
        dest = storage.episode_dir(podcast, episode) / f"audio{suffix}"
        shutil.move(staged, dest)
        episode.audio_path = storage.to_rel(dest)
        episode.downloaded_at = utcnow()
        session.add(episode)
        session.commit()
        session.refresh(episode)
        return episode
