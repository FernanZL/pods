"""The library view (collected episodes), audio uploads, and present-tense books."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import storage
from app.books import pipeline
from app.models import Book, Episode, Job, Podcast, utcnow
from app.services import audio
from tests.test_books_pipeline import _episode, _wait_ready


def _wait_job(client: TestClient, job_id: int, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.1)
    raise AssertionError("job did not finish")


# ------------------------------------------------------------------- collected episodes


def _catalog(session: Session) -> dict[str, int]:
    pod = Podcast(title="Show", rss_url="https://example.com/feed", slug="show")
    session.add(pod)
    session.commit()
    ids: dict[str, int] = {}
    for n, name in enumerate(["new", "downloaded", "indexed", "queued"], start=1):
        ep = Episode(
            podcast_id=pod.id, guid=name, number=n, title=f"Ep {name}", slug=f"{n:04d}-{name}",
            audio_url=f"https://example.com/{name}.mp3",
        )  # fmt: skip
        if name in ("downloaded", "indexed"):
            ep.downloaded_at = utcnow()
        if name == "indexed":
            ep.transcribed_at = ep.indexed_at = utcnow()
        session.add(ep)
        session.commit()
        assert ep.id is not None
        ids[name] = ep.id
    session.add(Job(kind="process", episode_id=ids["queued"], status="queued"))
    session.commit()
    return ids


def test_library_lists_only_collected_episodes(client: TestClient, session: Session) -> None:
    ids = _catalog(session)
    everything = client.get("/api/episodes").json()
    assert everything["total"] == 4

    mine = client.get("/api/episodes", params={"collected": "true"}).json()
    assert mine["total"] == 3
    assert {e["id"] for e in mine["items"]} == {ids["downloaded"], ids["indexed"], ids["queued"]}

    indexed = client.get("/api/episodes", params={"collected": "true", "status": "indexed"})
    assert [e["id"] for e in indexed.json()["items"]] == [ids["indexed"]]

    est = client.post("/api/episodes/estimate", json={"collected": True, "steps": ["index"]})
    assert est.status_code == 200
    assert est.json()["episode_count"] + est.json()["skipped_already_done"] == 3


# ---------------------------------------------------------------------------- uploads


def test_upload_becomes_a_processable_episode(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio, "probe_duration", lambda _p: 125.4)
    resp = client.post(
        "/api/episodes/upload",
        files={"file": ("My talk_2026.m4a", b"\x00" * 4096, "audio/mp4")},
        data={"title": "  A talk   I gave ", "description": "Recorded at home."},
    )
    assert resp.status_code == 201, resp.text
    ep = resp.json()
    assert ep["title"] == "A talk I gave"
    assert ep["status"] == "downloaded" and ep["duration_seconds"] == 125
    assert ep["podcast_title"] == "My uploads" and ep["number"] == 1

    row = session.get(Episode, ep["id"])
    assert row is not None and row.audio_path and row.audio_path.endswith("audio.m4a")
    assert row.audio_url == "upload://My talk_2026.m4a"
    assert storage.to_abs(row.audio_path).read_bytes() == b"\x00" * 4096
    assert not any(storage.to_abs("uploads-tmp").iterdir())  # staging cleaned up

    # it is in the library straight away, and served with its own media type
    mine = client.get("/api/episodes", params={"collected": "true"}).json()
    assert [e["id"] for e in mine["items"]] == [ep["id"]]
    assert client.get(f"/api/episodes/{ep['id']}/audio").headers["content-type"] in (
        "audio/mp4",
        "audio/x-m4a",
        "audio/mpeg",
    )

    # a second file in the same show is numbered after the first; a new show is separate
    second = client.post(
        "/api/episodes/upload", files={"file": ("b.mp3", b"\x01" * 10, "audio/mpeg")}
    ).json()
    assert second["number"] == 2 and second["title"] == "b"
    other = client.post(
        "/api/episodes/upload",
        files={"file": ("c.wav", b"\x02" * 10, "audio/wav")},
        data={"show": "Lectures"},
    ).json()
    assert other["podcast_title"] == "Lectures" and other["number"] == 1

    pod = session.get(Podcast, ep["podcast_id"])
    assert pod is not None and pod.rss_url == "upload://my-uploads"
    refresh = client.post(f"/api/podcasts/{pod.id}/refresh")
    assert refresh.status_code == 409

    # processing skips the download and runs transcribe + index on the uploaded file
    jobs = client.post("/api/episodes/process", json={"episode_ids": [ep["id"]]}).json()
    assert len(jobs) == 1
    assert _wait_job(client, jobs[0]["id"])["status"] == "done"
    detail = client.get(f"/api/episodes/{ep['id']}").json()
    assert detail["status"] == "indexed" and detail["local_audio"]

    # deleting local data keeps the uploaded audio (it is the only copy)
    assert client.delete(f"/api/episodes/{ep['id']}/data").status_code == 204
    detail = client.get(f"/api/episodes/{ep['id']}").json()
    assert detail["status"] == "downloaded" and detail["local_audio"]
    assert detail["segments"] == []

    # a forced re-run still uses the uploaded file instead of trying to download it
    forced = client.post(
        "/api/episodes/process", json={"episode_ids": [ep["id"]], "force": True}
    ).json()
    assert _wait_job(client, forced[0]["id"])["status"] == "done"


def test_upload_rejects_files_that_are_not_audio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_type = client.post(
        "/api/episodes/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert bad_type.status_code == 422 and "Unsupported file type" in bad_type.json()["detail"]

    empty = client.post("/api/episodes/upload", files={"file": ("a.mp3", b"", "audio/mpeg")})
    assert empty.status_code == 422

    def _unreadable(_p: Any) -> float:
        raise RuntimeError("ffprobe failed: Invalid data found when processing input")

    monkeypatch.setattr(audio, "probe_duration", _unreadable)
    broken = client.post("/api/episodes/upload", files={"file": ("a.mp3", b"zz", "audio/mpeg")})
    assert broken.status_code == 422 and "could not be read" in broken.json()["detail"]
    assert client.get("/api/episodes").json()["total"] == 0


# ---------------------------------------------------------------------- book tense


def test_present_tense_style_rules() -> None:
    base = {"speakers": "Andrew Huberman|Robert Greene"}
    past = pipeline.style({**base, "narrator": "Andrew Huberman"})
    assert "looking back on it" in past and "PRESENT" not in past

    present = pipeline.style({**base, "narrator": "Andrew Huberman", "tense": "present"})
    assert "as it happens, in the present tense" in present
    assert "Tense: PRESENT" in present and "I ask. Robert has an answer ready" in present
    assert "looking back on it" not in present

    narrated = pipeline.style({**base, "tense": "present"})
    assert "third person" in narrated and "Tense: PRESENT" in narrated


def test_book_told_in_the_present_tense(client: TestClient, session: Session) -> None:
    ep_id = _episode(session)
    bad = client.post("/api/books", json={"episode_id": ep_id, "tense": "future"})
    assert bad.status_code == 422

    created = client.post(
        "/api/books", json={"episode_id": ep_id, "narrator": "A", "tense": "present"}
    )
    assert created.status_code == 201
    assert created.json()["tense"] == "present" and created.json()["narrator"] == "Host"
    book = _wait_ready(client, created.json()["id"])
    assert book["status"] == "ready", book["error"]
    assert book["tense"] == "present"

    row = session.get(Book, book["id"])
    assert row is not None and row.dir_path
    data = json.loads((storage.to_abs(row.dir_path) / "book.json").read_text())
    assert data["tense"] == "present" and data["narrator"] == "Host"

    # the default stays the retrospective telling
    plain = client.post("/api/books", json={"episode_id": ep_id}).json()
    assert plain["tense"] == "past"
