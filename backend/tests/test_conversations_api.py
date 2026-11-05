"""Tests for /api/conversations CRUD endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.schemas import Citation, Scope
from app.services import conversations


def test_conversations_crud_flow(client: TestClient) -> None:
    assert client.get("/api/conversations").json() == []

    c1 = conversations.create_conversation(
        title="First chat",
        scope=Scope(podcast_ids=[1]),
    )
    assert c1.id is not None
    conversations.add_message(c1.id, "user", "Question one")

    c2 = conversations.create_conversation(title="Second chat")
    assert c2.id is not None
    conversations.add_message(c2.id, "user", "Question two")
    conversations.add_message(
        c2.id,
        "assistant",
        "Answer two [1]",
        citations=[
            Citation(
                n=1,
                episode_id=1,
                episode_title="Ep 1",
                podcast_title="Demo",
                speaker="Host",
                start=0.0,
                end=10.0,
                source="transcript",
                snippet="Snippet text",
            )
        ],
    )

    # Recent first: c2 updated after c1
    list_resp = client.get("/api/conversations")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert [it["id"] for it in items] == [c2.id, c1.id]
    assert items[0]["message_count"] == 2
    assert items[1]["message_count"] == 1

    # Detail
    detail_resp = client.get(f"/api/conversations/{c2.id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["title"] == "Second chat"
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["citations"][0]["speaker"] == "Host"

    # Patch c1 -> updates title & scope and moves c1 to most recent
    patch_resp = client.patch(
        f"/api/conversations/{c1.id}",
        json={"title": "Renamed chat", "scope": {"episode_ids": [2, 3]}},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["title"] == "Renamed chat"
    assert patched["scope"]["episode_ids"] == [2, 3]

    reordered = client.get("/api/conversations").json()
    assert [it["id"] for it in reordered] == [c1.id, c2.id]

    # Delete c2 -> 204 and messages gone
    del_resp = client.delete(f"/api/conversations/{c2.id}")
    assert del_resp.status_code == 204
    assert client.get(f"/api/conversations/{c2.id}").status_code == 404
    assert [it["id"] for it in client.get("/api/conversations").json()] == [c1.id]


def test_conversations_404_cases(client: TestClient) -> None:
    assert client.get("/api/conversations/4242").status_code == 404
    assert client.patch("/api/conversations/4242", json={"title": "Nope"}).status_code == 404
    assert client.delete("/api/conversations/4242").status_code == 404
