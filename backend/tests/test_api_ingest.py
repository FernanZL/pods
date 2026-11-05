"""Integration tests for ingest HTTP API routers (/podcasts, /episodes, /jobs)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import db, services
from app.domain import ProgressFn
from app.models import Episode, Job, utcnow
from app.services import transcribe


def _stub_rag_and_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_index_episode(
        episode_id: int,
        on_progress: ProgressFn,
        force: bool = False,
    ) -> int:
        del force
        on_progress(1.0, "Indexed")
        with db.session_scope() as s:
            ep = s.get(Episode, episode_id)
            if ep is not None:
                ep.indexed_at = utcnow()
                ep.passage_count = 3
                s.add(ep)
                s.commit()
        return 3

    def _fake_summarize_episode(
        episode_id: int,
        on_progress: ProgressFn,
        force: bool = False,
    ) -> Path:
        del episode_id, force
        on_progress(1.0, "Summarized")
        return Path("summary.md")

    try:
        from app.services import indexing as real_indexing

        monkeypatch.setattr(real_indexing, "index_episode", _fake_index_episode)
        monkeypatch.setattr(real_indexing, "remove_episode", lambda _id: 0)
    except ImportError:
        fake_idx = ModuleType("app.services.indexing")
        fake_idx.index_episode = _fake_index_episode  # type: ignore[attr-defined]
        fake_idx.remove_episode = lambda _id: 0  # type: ignore[attr-defined]
        fake_idx.rebuild_index = lambda on_progress: 0  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "app.services.indexing", fake_idx)
        monkeypatch.setattr(services, "indexing", fake_idx, raising=False)

    try:
        from app.services import summarize as real_summarize

        monkeypatch.setattr(real_summarize, "summarize_episode", _fake_summarize_episode)
    except ImportError:
        fake_sum = ModuleType("app.services.summarize")
        fake_sum.summarize_episode = _fake_summarize_episode  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "app.services.summarize", fake_sum)
        monkeypatch.setattr(services, "summarize", fake_sum, raising=False)

    try:
        import app.providers.fake  # noqa: F401
    except ImportError:
        monkeypatch.setattr(
            transcribe,
            "get_llm",
            lambda: SimpleNamespace(
                complete=lambda *_a, **_k: '{"A": "Andrew Huberman", "B": "Dr. Jane Doe"}'
            ),
        )


def _wait_job_done(client: TestClient, job_id: int, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    pytest.fail(f"Job {job_id} did not finish within {timeout}s")


def test_podcasts_endpoints_and_no_autofetch_on_empty_db(
    client: TestClient,
    fixtures_dir: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_rag_and_llm(monkeypatch)

    # Empty DB: GET /api/podcasts returns [] without touching the network
    initial = client.get("/api/podcasts")
    assert initial.status_code == 200
    assert initial.json() == []
    assert len(respx_mock.calls) == 0

    bad_url = "https://feeds.example.test/not-a-feed"
    respx_mock.get(bad_url).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    bad_resp = client.post("/api/podcasts", json={"rss_url": bad_url})
    assert bad_resp.status_code == 422

    rss_url = "https://feeds.example.test/science.xml"
    xml_text = (fixtures_dir / "feed.xml").read_text("utf-8")
    respx_mock.get(rss_url).mock(return_value=httpx.Response(200, text=xml_text))

    created = client.post("/api/podcasts", json={"rss_url": rss_url})
    assert created.status_code == 201
    pod = created.json()
    assert pod["title"] == "Science & Health Lab"
    assert pod["episode_count"] == 3
    assert pod["indexed_count"] == 0

    dup = client.post("/api/podcasts", json={"rss_url": rss_url})
    assert dup.status_code == 409

    refreshed = client.post(f"/api/podcasts/{pod['id']}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["episode_count"] == 3

    deleted = client.delete(f"/api/podcasts/{pod['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/podcasts").json() == []


def test_episodes_search_estimate_process_audio_and_delete_data(
    client: TestClient,
    fixtures_dir: Path,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_rag_and_llm(monkeypatch)

    rss_url = "https://feeds.example.test/science.xml"
    xml_text = (fixtures_dir / "feed.xml").read_text("utf-8")
    respx_mock.get(rss_url).mock(return_value=httpx.Response(200, text=xml_text))

    pod = client.post("/api/podcasts", json={"rss_url": rss_url}).json()

    ep_list = client.get("/api/episodes").json()
    assert ep_list["total"] == 3
    # Newest first: number 3, 2, 1
    assert [it["number"] for it in ep_list["items"]] == [3, 2, 1]

    # Keyword search in title vs description
    assert client.get("/api/episodes", params={"q": "Jane"}).json()["total"] == 0
    desc_hit = client.get(
        "/api/episodes",
        params={"q": "Jane", "search_description": "true"},
    ).json()
    assert desc_hit["total"] == 1
    ep_id = desc_hit["items"][0]["id"]

    est = client.post("/api/episodes/estimate", json={"episode_ids": [ep_id]})
    assert est.status_code == 200
    est_body = est.json()
    assert est_body["episode_count"] == 1
    assert est_body["known_minutes"] == 90.0
    assert est_body["total_usd"] > 0.0

    proc = client.post("/api/episodes/process", json={"episode_ids": [ep_id]})
    assert proc.status_code == 200
    jobs = proc.json()
    assert len(jobs) == 1
    done_job = _wait_job_done(client, jobs[0]["id"])
    assert done_job["status"] == "done"

    detail = client.get(f"/api/episodes/{ep_id}").json()
    assert detail["status"] == "indexed"
    assert detail["local_audio"] is True
    assert len(detail["segments"]) == 4

    audio_resp = client.get(f"/api/episodes/{ep_id}/audio")
    assert audio_resp.status_code == 200
    assert audio_resp.headers["content-type"].startswith("audio/mpeg")

    partial_resp = client.get(
        f"/api/episodes/{ep_id}/audio",
        headers={"Range": "bytes=0-99"},
    )
    assert partial_resp.status_code == 206
    assert len(partial_resp.content) == 100

    sum_resp = client.post(f"/api/episodes/{ep_id}/summarize")
    assert sum_resp.status_code == 200
    _wait_job_done(client, sum_resp.json()["id"])

    re_resp = client.post(f"/api/episodes/{ep_id}/reindex")
    assert re_resp.status_code == 200
    _wait_job_done(client, re_resp.json()["id"])

    wipe = client.delete(f"/api/episodes/{ep_id}/data")
    assert wipe.status_code == 204
    after_wipe = client.get(f"/api/episodes/{ep_id}").json()
    assert after_wipe["status"] == "new"
    assert after_wipe["local_audio"] is False
    assert after_wipe["segments"] == []

    assert client.delete(f"/api/podcasts/{pod['id']}").status_code == 204


def test_jobs_list_cancel_and_retry(
    client: TestClient,
    fixtures_dir: Path,
    session: Session,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_rag_and_llm(monkeypatch)

    rss_url = "https://feeds.example.test/science.xml"
    xml_text = (fixtures_dir / "feed.xml").read_text("utf-8")
    respx_mock.get(rss_url).mock(return_value=httpx.Response(200, text=xml_text))
    client.post("/api/podcasts", json={"rss_url": rss_url})
    ep_id = client.get("/api/episodes").json()["items"][0]["id"]

    failed = Job(
        kind="process",
        episode_id=ep_id,
        steps=["download"],
        status="failed",
        error="simulated error",
    )
    session.add(failed)
    session.commit()
    session.refresh(failed)
    assert failed.id is not None

    filtered = client.get("/api/jobs", params={"status": "failed"}).json()
    assert [j["id"] for j in filtered] == [failed.id]

    retried = client.post(f"/api/jobs/{failed.id}/retry")
    assert retried.status_code == 200
    retry_body = retried.json()
    assert retry_body["id"] != failed.id
    assert retry_body["steps"] == ["download"]
    _wait_job_done(client, retry_body["id"])

    cancelled = client.post(f"/api/jobs/{failed.id}/cancel")
    assert cancelled.status_code == 200
