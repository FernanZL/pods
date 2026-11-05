"""Tests for transcript chunking, vector indexing, summarization, and removal."""

from __future__ import annotations

from datetime import UTC, datetime

from app import db, storage
from app.domain import Segment, Transcript
from app.models import Episode, Podcast, utcnow
from app.services import indexing, summarize
from app.services.vectorstore import get_vector_store


def _seed_transcribed_episode(
    *,
    guid: str = "ep-1",
    number: int = 1,
    title: str = "Sleep Science",
    segments: list[Segment] | None = None,
) -> int:
    now = utcnow()
    if segments is None:
        segments = [
            Segment(
                speaker="A",
                start=0.0,
                end=12.0,
                text="Welcome to the episode on circadian biology and morning sunlight.",
            ),
            Segment(
                speaker="B",
                start=12.5,
                end=28.0,
                text="Morning light sets the circadian clock and regulates evening melatonin.",
            ),
            Segment(
                speaker="A",
                start=28.5,
                end=42.0,
                text="How does caffeine intake in the afternoon affect adenosine clearance?",
            ),
            Segment(
                speaker="B",
                start=42.5,
                end=60.0,
                text="Caffeine blocks adenosine receptors and reduces deep slow-wave sleep.",
            ),
        ]

    with db.session_scope() as session:
        podcast = session.get(Podcast, 1)
        if podcast is None:
            podcast = Podcast(
                title="Science Lab",
                rss_url="https://example.test/feed.xml",
                slug="science-lab",
            )
            session.add(podcast)
            session.flush()
        assert podcast.id is not None

        ep = Episode(
            podcast_id=podcast.id,
            guid=guid,
            number=number,
            title=title,
            slug=storage.episode_slug(number, title),
            published=datetime(2026, 2, 1, tzinfo=UTC),
            audio_url=f"https://example.test/{guid}.mp3",
            duration_seconds=600,
            downloaded_at=now,
            transcribed_at=now,
            speakers={"A": "Host", "B": "Guest"},
        )
        session.add(ep)
        session.flush()
        assert ep.id is not None

        ep_dir = storage.episode_dir(podcast, ep)
        t_path = ep_dir / "transcript.json"
        storage.write_transcript(
            t_path,
            Transcript(
                episode_id=ep.id,
                model="fake",
                speakers={"A": "Host", "B": "Guest"},
                segments=segments,
            ),
        )
        ep.transcript_path = storage.to_rel(t_path)
        session.add(ep)
        session.commit()
        return ep.id


def test_chunk_transcript_speaker_boundaries_and_overlap() -> None:
    segments = [
        Segment(
            "A",
            0.0,
            10.0,
            "Alpha sentence one about circadian light exposure in the morning.",
        ),
        Segment(
            "A",
            10.0,
            20.0,
            "Alpha sentence two explaining retinal ganglion cell signaling.",
        ),
        Segment(
            "B",
            20.0,
            30.0,
            "Beta turn starts here discussing evening melatonin onset timing.",
        ),
        Segment(
            "B",
            30.0,
            40.0,
            "Beta turn continues with cool bedroom temperature protocols.",
        ),
    ]
    transcript = Transcript(
        episode_id=7,
        model="fake",
        speakers={"A": "Host", "B": "Guest"},
        segments=segments,
    )

    # chunk_chars=230 fits A1+A2+B1 (~215 chars), while adding B2 overflows;
    # speaker boundary preference should break cleanly between A2 and B1!
    passages_no_overlap = indexing.chunk_transcript(
        transcript,
        chunk_chars=230,
        chunk_overlap_chars=0,
        podcast_id=2,
        episode_title="Sleep",
        podcast_title="Pod",
    )
    assert len(passages_no_overlap) == 2
    assert passages_no_overlap[0].id == "ep7:transcript:0"
    assert passages_no_overlap[0].metadata["speaker"] == "Host"
    assert passages_no_overlap[0].metadata["start"] == 0.0
    assert passages_no_overlap[0].metadata["end"] == 20.0
    assert "Guest:" not in passages_no_overlap[0].text

    assert passages_no_overlap[1].id == "ep7:transcript:1"
    assert passages_no_overlap[1].metadata["speaker"] == "Guest"
    assert passages_no_overlap[1].metadata["start"] == 20.0
    assert passages_no_overlap[1].metadata["end"] == 40.0

    # With overlap enabled (~90 chars), A2 overlaps into chunk 1 while Guest stays dominant
    passages_overlap = indexing.chunk_transcript(
        transcript,
        chunk_chars=230,
        chunk_overlap_chars=90,
    )
    assert len(passages_overlap) >= 2
    assert "Alpha sentence two" in passages_overlap[0].text
    assert "Alpha sentence two" in passages_overlap[1].text
    assert passages_overlap[1].metadata["speaker"] == "Guest"


def test_index_episode_idempotent_no_duplicates_and_remove() -> None:
    ep_id = _seed_transcribed_episode()
    store = get_vector_store()

    written = indexing.index_episode(ep_id)
    assert written >= 1
    assert store.count() == written
    assert ep_id in store.episode_ids()

    # Second call without force is a fast idempotent no-op
    assert indexing.index_episode(ep_id, force=False) == written
    assert store.count() == written

    # Force re-index deletes prior episode transcript vectors before upserting -> no duplicates
    assert indexing.index_episode(ep_id, force=True) == written
    assert store.count() == written

    # Summarize adds summary passages without duplicating or removing transcript passages
    summary_file = summarize.summarize_episode(ep_id)
    assert summary_file.exists()
    count_with_summary = store.count()
    assert count_with_summary > written

    # Force re-indexing transcript preserves summary passages without duplicating either
    indexing.index_episode(ep_id, force=True)
    assert store.count() == count_with_summary

    with db.session_scope() as session:
        ep = session.get(Episode, ep_id)
        assert ep is not None
        assert ep.indexed_at is not None
        assert ep.summarized_at is not None
        assert ep.passage_count == count_with_summary

    removed = indexing.remove_episode(ep_id)
    assert removed == count_with_summary
    assert store.count() == 0

    with db.session_scope() as session:
        ep = session.get(Episode, ep_id)
        assert ep is not None
        assert ep.indexed_at is None
        assert ep.passage_count == 0


def test_rebuild_index_reembeds_existing_transcripts_only() -> None:
    ep1_id = _seed_transcribed_episode(guid="ep-1", number=1, title="Episode One")
    summarize.summarize_episode(ep1_id)

    # Create a second episode that has NO transcript on disk
    with db.session_scope() as session:
        untranscribed = Episode(
            podcast_id=1,
            guid="ep-2",
            number=2,
            title="Untranscribed Episode",
            slug=storage.episode_slug(2, "Untranscribed Episode"),
            audio_url="https://example.test/ep-2.mp3",
        )
        session.add(untranscribed)
        session.commit()
        untranscribed_id = untranscribed.id
        assert untranscribed_id is not None

    indexing.remove_episode(ep1_id)
    assert get_vector_store().count() == 0

    rebuilt = indexing.rebuild_index()
    assert rebuilt >= 2
    assert get_vector_store().episode_ids() == {ep1_id}
