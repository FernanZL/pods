"""Offline tests for episode audio downloading (fake mode and respx streaming)."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlmodel import Session

from app import storage
from app.config import get_settings
from app.models import Episode, Podcast
from app.services.downloader import FAKE_PLACEHOLDER_BYTES, download_episode


def _seed_episode(session: Session) -> Episode:
    podcast = Podcast(
        title="Test Podcast",
        rss_url="https://feeds.example.test/rss.xml",
        slug="test-podcast",
    )
    session.add(podcast)
    session.flush()
    assert podcast.id is not None
    episode = Episode(
        podcast_id=podcast.id,
        guid="guid-1",
        number=1,
        title="Test Episode",
        slug="0001-test-episode",
        audio_url="https://cdn.example.test/audio/ep1.mp3",
    )
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


def test_download_episode_fake_mode_writes_placeholder(session: Session) -> None:
    ep = _seed_episode(session)
    assert ep.id is not None

    dest = download_episode(ep.id)
    assert dest.is_file()
    assert dest.stat().st_size == FAKE_PLACEHOLDER_BYTES

    session.expire_all()
    refreshed = session.get(Episode, ep.id)
    assert refreshed is not None
    assert refreshed.downloaded_at is not None
    assert refreshed.audio_path == storage.to_rel(dest)

    dest.write_bytes(b"custom")
    again = download_episode(ep.id, force=False)
    assert again == dest
    assert dest.read_bytes() == b"custom"


def test_download_episode_real_mode_streams_and_reports_progress(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    monkeypatch.setenv("DOWNLOAD_MODE", "real")
    get_settings.cache_clear()

    ep = _seed_episode(session)
    assert ep.id is not None

    payload = b"M" * (2 * 1024 * 1024 + 123)
    respx_mock.get(ep.audio_url).mock(
        return_value=httpx.Response(
            200,
            content=payload,
            headers={"Content-Length": str(len(payload))},
        )
    )

    progress_events: list[tuple[float, str]] = []
    dest = download_episode(
        ep.id,
        on_progress=lambda frac, msg: progress_events.append((frac, msg)),
    )

    assert dest.read_bytes() == payload
    assert not dest.with_name("audio.mp3.part").exists()
    assert progress_events[0][0] == 0.0
    assert progress_events[-1][0] == 1.0
    assert any(0.0 < frac < 1.0 for frac, _ in progress_events)


def test_download_episode_deletes_partial_on_error(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    monkeypatch.setenv("DOWNLOAD_MODE", "real")
    get_settings.cache_clear()

    ep = _seed_episode(session)
    assert ep.id is not None
    podcast = session.get(Podcast, ep.podcast_id)
    assert podcast is not None
    ep_dir = storage.episode_dir(podcast, ep)

    respx_mock.get(ep.audio_url).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        download_episode(ep.id)

    assert not (ep_dir / "audio.mp3").exists()
    assert not (ep_dir / "audio.mp3.part").exists()

    payload = b"X" * (2 * 1024 * 1024)
    respx_mock.get(ep.audio_url).mock(
        return_value=httpx.Response(
            200,
            content=payload,
            headers={"Content-Length": str(len(payload))},
        )
    )

    def _abort_midway(frac: float, _msg: str) -> None:
        if frac > 0.0:
            raise RuntimeError("cancelled mid-download")

    with pytest.raises(RuntimeError, match="cancelled mid-download"):
        download_episode(ep.id, on_progress=_abort_midway)

    assert not (ep_dir / "audio.mp3").exists()
    assert not (ep_dir / "audio.mp3.part").exists()
