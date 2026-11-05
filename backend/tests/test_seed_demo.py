"""Tests for offline demo seeding script (scripts/seed_demo.py)."""

from __future__ import annotations

import pytest
from sqlmodel import select

from app import db, storage
from app.config import get_settings
from app.models import Episode, Podcast
from app.providers import get_embedder, reset_providers
from app.services.vectorstore import get_vector_store, reset_vector_store
from scripts.seed_demo import DEMO_PODCAST_RSS, DEMO_PODCAST_TITLE, main, seed_demo


def test_seed_demo_creates_three_indexed_episodes_and_is_idempotent() -> None:
    pod = seed_demo()
    assert pod.title == DEMO_PODCAST_TITLE
    assert pod.rss_url == DEMO_PODCAST_RSS

    store = get_vector_store()
    first_count = store.count()
    assert first_count > 0

    with db.session_scope() as session:
        podcasts = session.exec(select(Podcast)).all()
        episodes = session.exec(select(Episode).order_by(Episode.number)).all()
        assert len(podcasts) == 1
        assert len(episodes) == 3

        for ep in episodes:
            assert ep.downloaded_at is not None
            assert ep.transcribed_at is not None
            assert ep.indexed_at is not None
            assert ep.passage_count > 0
            assert ep.speakers == {"A": "Host", "B": "Guest"}
            assert ep.transcript_path is not None

            t_file = storage.to_abs(ep.transcript_path)
            assert t_file.exists()
            assert t_file.with_suffix(".md").exists()
            transcript = storage.read_transcript(t_file)
            assert len(transcript.segments) >= 24
            assert {seg.speaker for seg in transcript.segments} == {"A", "B"}

    # Running a second time is completely idempotent (no duplicate rows or vectors)
    assert main([]) == 0
    assert store.count() == first_count
    with db.session_scope() as session:
        assert len(session.exec(select(Podcast)).all()) == 1
        assert len(session.exec(select(Episode)).all()) == 3


def test_seed_demo_topical_retrieval_with_fake_embedder() -> None:
    seed_demo()
    store = get_vector_store()
    embedder = get_embedder()

    with db.session_scope() as session:
        eps = {ep.number: ep.id for ep in session.exec(select(Episode)).all()}

    sleep_vec = embedder.embed(["morning sunlight circadian melatonin adenosine sleep"])[0]
    dopamine_vec = embedder.embed(["phasic dopamine baseline reward prediction motivation"])[0]
    exercise_vec = embedder.embed(["zone two aerobic vo2 max resistance hypertrophy"])[0]

    assert store.query(sleep_vec, k=1)[0].passage.metadata["episode_id"] == eps[1]
    assert store.query(dopamine_vec, k=1)[0].passage.metadata["episode_id"] == eps[2]
    assert store.query(exercise_vec, k=1)[0].passage.metadata["episode_id"] == eps[3]


def test_seed_demo_refuses_paid_embedder_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
    get_settings.cache_clear()
    reset_providers()
    reset_vector_store()

    with pytest.raises(RuntimeError, match="allow-paid"):
        seed_demo(allow_paid=False)

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 1
