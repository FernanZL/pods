"""Episode audio downloader (real streaming via httpx + offline fake mode)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from app import db, storage
from app.config import get_settings
from app.domain import ProgressFn
from app.models import Episode, Podcast, utcnow

CHUNK_SIZE = 1024 * 1024  # 1 MiB
FAKE_PLACEHOLDER_BYTES = 1024  # 1 KiB


def _noop_progress(_fraction: float, _message: str) -> None:
    return None


def download_episode(
    episode_id: int,
    on_progress: ProgressFn = _noop_progress,
    force: bool = False,
) -> Path:
    """Download episode audio to audio.mp3 (or 1 KB placeholder in fake mode)."""
    with db.session_scope() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"Episode {episode_id} not found")
        podcast = session.get(Podcast, episode.podcast_id)
        if podcast is None:
            raise ValueError(f"Podcast {episode.podcast_id} not found")

        if not force and episode.downloaded_at is not None and episode.audio_path:
            existing = storage.to_abs(episode.audio_path)
            if existing.is_file():
                on_progress(1.0, "Audio already downloaded")
                return existing

        if episode.audio_url.startswith("upload://"):
            # An uploaded file has nowhere to be downloaded from, even when forced.
            existing = storage.to_abs(episode.audio_path) if episode.audio_path else None
            if existing is not None and existing.is_file():
                on_progress(1.0, "Using the uploaded audio")
                return existing
            raise ValueError("The uploaded audio file is missing. Upload it again.")

        ep_dir = storage.episode_dir(podcast, episode)
        audio_url = episode.audio_url

    dest = ep_dir / "audio.mp3"
    part_path = ep_dir / "audio.mp3.part"
    settings = get_settings()

    if settings.download_mode == "fake":
        on_progress(0.0, "Writing placeholder audio")
        try:
            part_path.write_bytes(b"\x00" * FAKE_PLACEHOLDER_BYTES)
            part_path.replace(dest)
        except BaseException:
            part_path.unlink(missing_ok=True)
            raise
        on_progress(1.0, "Placeholder audio written")
    else:
        parsed = urlparse(audio_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid audio URL: {audio_url!r}")

        on_progress(0.0, "Starting audio download")
        try:
            timeout = httpx.Timeout(60.0, connect=30.0)
            with httpx.stream(
                "GET", audio_url.strip(), follow_redirects=True, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                raw_len = resp.headers.get("content-length")
                total = int(raw_len) if raw_len and raw_len.isdigit() else 0
                downloaded = 0
                with part_path.open("wb") as out_file:
                    for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        done_mb = downloaded / CHUNK_SIZE
                        if total > 0:
                            frac = min(downloaded / total, 0.99)
                            total_mb = total / CHUNK_SIZE
                            on_progress(frac, f"Downloaded {done_mb:.1f} / {total_mb:.1f} MiB")
                        else:
                            on_progress(0.0, f"Downloaded {done_mb:.1f} MiB")
            part_path.replace(dest)
        except BaseException:
            part_path.unlink(missing_ok=True)
            raise
        on_progress(1.0, "Download complete")

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.audio_path = storage.to_rel(dest)
            ep.downloaded_at = utcnow()
            session.add(ep)
            session.commit()

    return dest
