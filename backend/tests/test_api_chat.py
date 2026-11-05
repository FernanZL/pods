"""HTTP SSE tests for POST /api/chat and /api/index endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from scripts.seed_demo import seed_demo


def _parse_sse(raw_body: str) -> list[tuple[str, dict[str, Any]]]:
    normalized = raw_body.replace("\r\n", "\n")
    events: list[tuple[str, dict[str, Any]]] = []
    for block in normalized.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip() and not ln.startswith(":")]
        if not lines:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("event:"):
                event_name = line.partition(":")[2].strip()
            elif line.startswith("data:"):
                data_lines.append(line.partition(":")[2].strip())
        if data_lines:
            payload = json.loads("\n".join(data_lines))
            events.append((event_name, payload))
    return events


def test_api_chat_empty_index_sse(client: TestClient) -> None:
    resp = client.post("/api/chat", json={"message": "Tell me about sleep"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    events = _parse_sse(resp.text)
    names = [name for name, _ in events]
    assert names == ["meta", "citations", "token", "done"]
    assert events[1][1]["citations"] == []
    assert "library" in events[2][1]["text"].lower()


def test_api_chat_with_seeded_index_and_stats(client: TestClient) -> None:
    seed_demo()

    stats_resp = client.get("/api/index/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["podcasts"] == 1
    assert stats["episodes_total"] == 3
    assert stats["episodes_indexed"] == 3
    assert stats["passages"] > 0
    assert stats["embedding_model"] == "fake-hash-256"
    assert stats["hours_indexed"] > 0.0

    resp = client.post(
        "/api/chat",
        json={"message": "How does morning sunlight regulate circadian sleep and melatonin?"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert len(events) >= 4
    assert events[0][0] == "meta"
    assert events[1][0] == "citations"
    assert events[-1][0] == "done"
    assert all(ev_name == "token" for ev_name, _ in events[2:-1])

    streamed_answer = "".join(payload["text"] for ev_name, payload in events if ev_name == "token")
    assert "[1]" in streamed_answer
    assert "[2]" in streamed_answer
    assert len(events[1][1]["citations"]) >= 2
    assert len(events[-1][1]["citations"]) == 2


def test_api_chat_unknown_conversation_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/chat",
        json={"conversation_id": 99999, "message": "Follow up"},
    )
    assert resp.status_code == 404


def test_api_index_rebuild_enqueues_job(client: TestClient) -> None:
    seed_demo()
    resp = client.post("/api/index/rebuild")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "rebuild_index"
    assert body["episode_id"] is None
