"""Book pipeline: fake-mode end to end through the API, and the LLM path with a stub model."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlmodel import Session

from app import storage
from app.books import pipeline
from app.domain import Segment, Transcript
from app.models import Book, Episode, Podcast


def _episode(session: Session, n_segments: int = 30) -> int:
    pod = Podcast(title="Demo Podcast", rss_url="demo://p", slug="demo-podcast")
    session.add(pod)
    session.commit()
    ep = Episode(
        podcast_id=pod.id, guid="g", number=7, title="Light and sleep", slug="0007-light",
        audio_url="x", description="A talk about light.",
    )  # fmt: skip
    session.add(ep)
    session.commit()
    segs = [
        Segment(
            "A" if i % 2 == 0 else "B",
            i * 30.0,
            i * 30.0 + 28,
            f"Segment number {i} explains how morning light and evening darkness shape the clock "
            f"for people who sleep badly, case {i}.",
        )
        for i in range(n_segments)
    ]
    tr = Transcript(episode_id=ep.id, model="fake", speakers={"A": "Host", "B": "Guest"},
                    segments=segs)  # fmt: skip
    path = storage.episode_dir(pod, ep) / "transcript.json"
    storage.write_transcript(path, tr)
    ep.transcript_path = storage.to_rel(path)
    session.add(ep)
    session.commit()
    assert ep.id is not None
    return ep.id


def _wait_ready(client, book_id: int, timeout: float = 30) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/books/{book_id}").json()
        if body["status"] in ("ready", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError("book did not finish")


def test_fake_book_end_to_end(client, session) -> None:
    ep_id = _episode(session)
    est = client.post("/api/books/estimate", json={"episode_id": ep_id}).json()
    assert est["llm_usd"] == 0.0 and est["chapters"] >= 3

    created = client.post("/api/books", json={"episode_id": ep_id})
    assert created.status_code == 201
    book = _wait_ready(client, created.json()["id"])
    assert book["status"] == "ready", book["error"]
    assert book["pages"] > 3 and book["chapters"] >= 3 and book["quotes"] > 0

    pdf = client.get(f"/api/books/{book['id']}/pdf?download=true")
    assert pdf.content[:5] == b"%PDF-"
    assert "attachment" in pdf.headers["content-disposition"]
    assert client.get(f"/api/books/{book['id']}/cover.png").headers["content-type"] == "image/png"

    reshuffled = client.post(f"/api/books/{book['id']}/reshuffle").json()
    assert reshuffled["seed"] != book["seed"] and reshuffled["status"] == "ready"

    assert client.delete(f"/api/books/{book['id']}").status_code == 204
    assert client.get(f"/api/books/{book['id']}").status_code == 404


def test_book_requires_a_transcript(client, session) -> None:
    pod = Podcast(title="P", rss_url="demo://q", slug="p")
    session.add(pod)
    session.commit()
    ep = Episode(podcast_id=pod.id, guid="x", number=1, title="T", slug="0001-t", audio_url="u")
    session.add(ep)
    session.commit()
    assert client.post("/api/books", json={"episode_id": ep.id}).status_code == 409


class _StubLLM:
    """Plays the planner, then the section writer; one invented quote per section."""

    model = "stub"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, messages, *, max_tokens=None, json_object=False) -> str:
        system = messages[0]["content"]
        if "planning a long-form" in system:
            self.calls.append("plan")
            return json.dumps(
                {
                    "title": "The Clock Inside",
                    "title_accent": "Inside",
                    "deck": "On light.",
                    "closing_quote": "Segment number 29 explains how morning light",
                    "glossary": [{"term": "clock", "definition": "the body's timer"}],
                    "chapters": [
                        {
                            "title": "Mornings",
                            "dek": "d",
                            "opener_quote": "Segment number 3 explains how morning light and evening darkness shape the clock",
                            "sections": [
                                {"heading": "A", "brief": "b", "first": 0, "last": 9},
                                {"heading": "B", "brief": "b", "first": 10, "last": 14},
                            ],
                        },
                        {
                            "title": "Evenings",
                            "dek": "d",
                            "opener_quote": "not in the transcript at all",
                            "sections": [{"heading": "C", "brief": "b", "first": 15, "last": 25}],
                        },
                    ],
                }  # fmt: skip
            )
        self.calls.append("section")
        slice_first = int(messages[1]["content"].split("TRANSCRIPT SLICE:\n[")[1].split("]")[0])
        return json.dumps(
            {
                "blocks": [
                    {
                        "type": "p",
                        "text": f"The guest says ⟦Segment number {slice_first} explains "
                        "how morning light⟧ and also ⟦light cures everything forever⟧.",
                    },
                    {"type": "pull", "quote": "an invented pull quote that nobody said"},
                    {
                        "type": "callout",
                        "title": "From the episode",
                        "items": ["Go outside", "Dim lamps"],
                    },
                ]
            }  # fmt: skip
        )

    def stream(self, messages, *, max_tokens=None):
        yield ""


def test_llm_path_verifies_quotes_and_covers_the_tail(session, monkeypatch, settings) -> None:
    ep_id = _episode(session)
    stub = _StubLLM()
    monkeypatch.setattr(pipeline, "get_llm", lambda: stub)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    book = Book(episode_id=ep_id, seed=5)
    session.add(book)
    session.commit()
    assert book.id is not None

    pipeline.build_book(book.id, on_progress=lambda f, m: None)

    session.expire_all()
    row = session.get(Book, book.id)
    assert row is not None and row.status == "ready"
    assert stub.calls.count("plan") == 1 and stub.calls.count("section") == 3
    assert row.quotes == 3  # one verified inline quote per section
    assert row.rejected_quotes == 6  # invented inline + invented pull, per section
    data = json.loads((storage.to_abs(row.dir_path) / "book.json").read_text())
    # the last section was stretched to the end of the conversation
    assert data["chapters"][-1]["end"] == 29 * 30.0 + 28
    # unverifiable opener falls back (no pull survived) -> None; verified one is kept
    assert data["chapters"][0]["opener"]["speaker"] == "Guest"  # segment 3 is the guest
    assert data["chapters"][1]["opener"] is None
    plan = json.loads((storage.to_abs(row.dir_path) / "plan.json").read_text())
    assert all(s["target_words"] >= 250 for c in plan["chapters"] for s in c["sections"])


def test_housekeeping_closers_are_refused_and_minor_speakers_dropped() -> None:
    from app.books.document import Quote

    tr = Transcript(
        episode_id=1, model="m", speakers={"A": "Host", "B": "Guest", "@": "Speaker @"},
        segments=[Segment("A", 0, 300, "intro " * 50), Segment("B", 300, 900, "talk " * 200),
                  Segment("@", 900, 901, "noise")],
    )  # fmt: skip
    assert pipeline.main_speakers(tr) == ["Host", "Guest"]
    outro = Quote("Thank you for joining me for today's discussion with the guest.", "Host", 890)
    assert pipeline._is_housekeeping(outro, 901)
    assert not pipeline._is_housekeeping(
        Quote("Attention makes ordinary things strange.", "Guest", 400), 901
    )
