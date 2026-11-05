"""Offline tests for RSS feed parsing and podcast synchronization."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from sqlmodel import Session, select

from app.models import Episode, utcnow
from app.services.feeds import parse_duration, parse_feed, strip_html, sync_podcast


def test_parse_duration_formats() -> None:
    assert parse_duration("01:30:00") == 5400
    assert parse_duration("45:30") == 2730
    assert parse_duration("1800") == 1800
    assert parse_duration(90) == 90
    assert parse_duration("") is None
    assert parse_duration(None) is None
    assert parse_duration("invalid") is None


def test_strip_html_removes_tags_and_scripts() -> None:
    raw = "<p>Hello <b>world</b> &amp; friends.</p><script>evil()</script><p>Next line.</p>"
    assert strip_html(raw) == "Hello world & friends. Next line."


def test_parse_feed_fixture(fixtures_dir: Path) -> None:
    xml_text = (fixtures_dir / "feed.xml").read_text("utf-8")
    parsed = parse_feed(xml_text)

    assert parsed.title == "Science & Health Lab"
    assert parsed.description == "Evidence-based tools for sleep, focus & longevity."
    assert parsed.image_url == "https://example.test/cover.jpg"
    assert len(parsed.episodes) == 3

    newest, middle, oldest = parsed.episodes
    assert newest.number == 3
    assert newest.guid == "ep-guid-3"
    assert newest.duration_seconds == 5400
    assert "<strong>" not in newest.description
    assert "Guest: Dr. Jane Doe." in newest.description
    assert newest.slug.startswith("0003-")

    assert middle.number == 2
    assert middle.duration_seconds == 2730
    assert middle.slug.startswith("0002-")

    assert oldest.number == 1
    assert oldest.duration_seconds == 1800
    assert oldest.slug == "0001-neuroplasticity-fundamentals"


def test_parse_feed_guid_fallback_and_invalid_inputs() -> None:
    minimal_rss = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Minimal Show</title>
        <item>
          <title>No GUID Episode</title>
          <enclosure url="https://cdn.example.test/only.mp3" type="audio/mpeg" />
        </item>
      </channel>
    </rss>"""
    parsed = parse_feed(minimal_rss)
    assert len(parsed.episodes) == 1
    assert parsed.episodes[0].guid == "https://cdn.example.test/only.mp3"
    assert parsed.episodes[0].number == 1

    for bad in ("", "not xml at all", "<html><head><title>Web Page</title></head></html>"):
        with pytest.raises(ValueError):
            parse_feed(bad)


def test_sync_podcast_upserts_without_clobbering_pipeline_state(
    fixtures_dir: Path,
    session: Session,
    respx_mock: respx.MockRouter,
) -> None:
    feed_url = "https://feeds.example.test/science.xml"
    xml_v1 = (fixtures_dir / "feed.xml").read_text("utf-8")
    respx_mock.get(feed_url).mock(return_value=httpx.Response(200, text=xml_v1))

    podcast = sync_podcast(feed_url)
    assert podcast.slug == "science-health-lab"

    episodes = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
    assert len(episodes) == 3

    oldest = next(ep for ep in episodes if ep.guid == "ep-guid-1")
    ts = utcnow()
    oldest.downloaded_at = ts
    oldest.audio_path = "podcasts/science-health-lab/0001-neuroplasticity-fundamentals/audio.mp3"
    oldest.transcribed_at = ts
    oldest.speakers = {"A": "Dr. Host"}
    session.add(oldest)
    session.commit()

    new_item = """
    <item>
      <title>Brand New Episode</title>
      <guid isPermaLink="false">ep-guid-4</guid>
      <pubDate>Fri, 26 Sep 2025 08:00:00 +0000</pubDate>
      <description>Fresh release.</description>
      <enclosure url="https://cdn.example.test/episodes/ep4.mp3" type="audio/mpeg" />
      <itunes:duration>00:20:00</itunes:duration>
    </item>
    """
    xml_v2 = xml_v1.replace("<item>", f"{new_item}\n    <item>", 1)
    respx_mock.get(feed_url).mock(return_value=httpx.Response(200, text=xml_v2))

    sync_podcast(feed_url)
    session.expire_all()

    updated_eps = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
    assert len(updated_eps) == 4

    by_guid = {ep.guid: ep for ep in updated_eps}
    assert by_guid["ep-guid-4"].number == 4
    preserved = by_guid["ep-guid-1"]
    assert preserved.number == 1
    assert preserved.downloaded_at is not None
    assert preserved.transcribed_at is not None
    assert preserved.speakers == {"A": "Dr. Host"}

    second_url = "https://feeds.example.test/duplicate-title.xml"
    respx_mock.get(second_url).mock(return_value=httpx.Response(200, text=xml_v1))
    second_podcast = sync_podcast(second_url)
    assert second_podcast.slug == "science-health-lab-2"
