"""Offline tests for JobWorker, selection resolution, and cost estimation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session

from app import db, services
from app.domain import ProgressFn
from app.jobs.worker import (
    JobWorker,
    create_jobs,
    resolve_selection,
)
from app.models import Episode, Job, Podcast, utcnow
from app.schemas import SelectionRequest
from app.services import transcribe
from app.services.estimate import estimate


def _install_fake_rag_modules(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"index": 0, "summarize": 0, "rebuild": 0}

    def fake_index_episode(
        episode_id: int,
        on_progress: ProgressFn,
        force: bool = False,
    ) -> int:
        del force
        counts["index"] += 1
        on_progress(0.5, "Indexing passages")
        with db.session_scope() as s:
            ep = s.get(Episode, episode_id)
            if ep is not None:
                ep.indexed_at = utcnow()
                ep.passage_count = 4
                s.add(ep)
                s.commit()
        on_progress(1.0, "Indexed")
        return 4

    def fake_summarize_episode(
        episode_id: int,
        on_progress: ProgressFn,
        force: bool = False,
    ) -> Path:
        del force
        counts["summarize"] += 1
        on_progress(1.0, "Summarized")
        with db.session_scope() as s:
            ep = s.get(Episode, episode_id)
            if ep is not None:
                ep.summarized_at = utcnow()
                s.add(ep)
                s.commit()
        return Path("summary.md")

    def fake_rebuild_index(on_progress: ProgressFn) -> int:
        counts["rebuild"] += 1
        on_progress(1.0, "Rebuilt")
        return 10

    try:
        from app.services import indexing as real_indexing

        monkeypatch.setattr(real_indexing, "index_episode", fake_index_episode)
        monkeypatch.setattr(real_indexing, "rebuild_index", fake_rebuild_index)
    except ImportError:
        fake_mod = ModuleType("app.services.indexing")
        fake_mod.index_episode = fake_index_episode  # type: ignore[attr-defined]
        fake_mod.rebuild_index = fake_rebuild_index  # type: ignore[attr-defined]
        fake_mod.remove_episode = lambda _ep_id: 0  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "app.services.indexing", fake_mod)
        monkeypatch.setattr(services, "indexing", fake_mod, raising=False)

    try:
        from app.services import summarize as real_summarize

        monkeypatch.setattr(real_summarize, "summarize_episode", fake_summarize_episode)
    except ImportError:
        fake_sum = ModuleType("app.services.summarize")
        fake_sum.summarize_episode = fake_summarize_episode  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "app.services.summarize", fake_sum)
        monkeypatch.setattr(services, "summarize", fake_sum, raising=False)

    monkeypatch.setattr(
        transcribe,
        "get_llm",
        lambda: SimpleNamespace(complete=lambda *_a, **_k: '{"A": "Host", "B": "Guest"}'),
    )
    return counts


def _seed_two_episodes(session: Session) -> tuple[Episode, Episode]:
    pod = Podcast(
        title="Lab Podcast",
        rss_url="https://feeds.example.test/lab.xml",
        slug="lab-podcast",
    )
    session.add(pod)
    session.flush()
    assert pod.id is not None
    ep1 = Episode(
        podcast_id=pod.id,
        guid="g1",
        number=1,
        title="Sleep Toolkit",
        slug="0001-sleep-toolkit",
        description="Circadian rhythm essentials.",
        audio_url="https://cdn.example.test/1.mp3",
        duration_seconds=3600,
    )
    ep2 = Episode(
        podcast_id=pod.id,
        guid="g2",
        number=2,
        title="Focus & Dopamine",
        slug="0002-focus-dopamine",
        description="Neurochemistry of motivation.",
        audio_url="https://cdn.example.test/2.mp3",
        duration_seconds=None,
    )
    session.add(ep1)
    session.add(ep2)
    session.commit()
    session.refresh(ep1)
    session.refresh(ep2)
    return ep1, ep2


def test_selection_estimate_and_job_deduplication(session: Session) -> None:
    ep1, ep2 = _seed_two_episodes(session)
    assert ep1.id is not None and ep2.id is not None

    matched_title = resolve_selection(session, SelectionRequest(q="dopamine"))
    assert [e.id for e in matched_title] == [ep2.id]

    matched_desc = resolve_selection(
        session,
        SelectionRequest(q="circadian", search_description=True),
    )
    assert [e.id for e in matched_desc] == [ep1.id]

    now = utcnow()
    ep2.downloaded_at = now
    ep2.transcribed_at = now
    ep2.indexed_at = now
    session.add(ep2)
    session.commit()

    est = estimate(SelectionRequest(podcast_id=ep1.podcast_id))
    assert est.episode_count == 1
    assert est.skipped_already_done == 1
    assert est.known_minutes == 60.0
    assert est.unknown_duration_count == 0
    assert est.total_usd > 0.0

    jobs = create_jobs(SelectionRequest(podcast_id=ep1.podcast_id))
    assert len(jobs) == 1
    assert jobs[0].episode_id == ep1.id

    # Duplicate active job for ep1 is skipped
    dup = create_jobs(SelectionRequest(episode_ids=[ep1.id], force=True))
    assert dup == []

    # Force=True creates a job for already-completed ep2
    forced = create_jobs(SelectionRequest(episode_ids=[ep2.id], force=True))
    assert len(forced) == 1
    assert forced[0].episode_id == ep2.id


async def test_worker_runs_jobs_and_resumes_stale_running_job(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _install_fake_rag_modules(monkeypatch)
    ep1, ep2 = _seed_two_episodes(session)
    assert ep1.id is not None and ep2.id is not None

    stale = Job(
        kind="process",
        episode_id=ep1.id,
        steps=["download", "transcribe", "index"],
        status="running",
        message="Interrupted",
    )
    session.add(stale)
    session.commit()
    session.refresh(stale)
    assert stale.id is not None

    local_worker = JobWorker()
    await local_worker.start()
    try:
        sum_job = Job(kind="summarize", episode_id=ep2.id, status="queued")
        re_job = Job(kind="rebuild_index", status="queued")
        session.add(sum_job)
        session.add(re_job)
        session.commit()
        session.refresh(sum_job)
        session.refresh(re_job)
        assert sum_job.id is not None and re_job.id is not None

        local_worker.enqueue(sum_job.id)
        local_worker.enqueue(re_job.id)
        await local_worker.wait_for_idle(timeout=5.0)
    finally:
        await local_worker.stop()

    session.expire_all()
    done_stale = session.get(Job, stale.id)
    done_sum = session.get(Job, sum_job.id)
    done_re = session.get(Job, re_job.id)
    assert done_stale is not None and done_stale.status == "done"
    assert done_sum is not None and done_sum.status == "done"
    assert done_re is not None and done_re.status == "done"
    assert counts == {"index": 1, "summarize": 1, "rebuild": 1}


async def test_worker_cancel_and_failure_recording(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_rag_modules(monkeypatch)
    ep1, ep2 = _seed_two_episodes(session)
    assert ep1.id is not None and ep2.id is not None

    local_worker = JobWorker()

    def _cancelling_download(
        _ep_id: int,
        on_progress: ProgressFn = lambda _f, _m: None,
        force: bool = False,
    ) -> Any:
        del force
        on_progress(0.2, "Started")
        assert cancel_target.id is not None
        local_worker.cancel(cancel_target.id)
        on_progress(0.5, "Should raise JobCancelled")
        return Path("unreachable.mp3")

    cancel_target = Job(
        kind="process",
        episode_id=ep1.id,
        steps=["download"],
        status="queued",
    )
    session.add(cancel_target)
    session.commit()
    session.refresh(cancel_target)
    assert cancel_target.id is not None

    monkeypatch.setattr("app.jobs.worker.download_episode", _cancelling_download)

    await local_worker.start()
    try:
        await local_worker.wait_for_idle(timeout=5.0)
    finally:
        await local_worker.stop()

    session.expire_all()
    cancelled = session.get(Job, cancel_target.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    def _failing_download(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("disk quota exceeded")

    monkeypatch.setattr("app.jobs.worker.download_episode", _failing_download)

    fail_job = Job(
        kind="process",
        episode_id=ep2.id,
        steps=["download"],
        status="queued",
    )
    session.add(fail_job)
    session.commit()
    session.refresh(fail_job)
    assert fail_job.id is not None

    await local_worker.start()
    try:
        await local_worker.wait_for_idle(timeout=5.0)
    finally:
        await local_worker.stop()

    session.expire_all()
    failed = session.get(Job, fail_job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "disk quota exceeded"
    assert "Traceback" not in (failed.error or "")
