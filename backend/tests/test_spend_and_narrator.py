"""Measured API spend, and books told in a speaker's first person."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session

from app import spend, storage
from app.books import pipeline
from app.domain import Segment, Transcript
from app.models import Book, Episode
from app.providers.transcription.openai_diarize import OpenAIDiarizeTranscriber
from app.services import audio, transcribe
from app.services.estimate import transcription_rate
from tests.test_books_pipeline import _episode, _StubLLM, _wait_ready
from tests.test_transcribe import _seed_episode
from tests.test_transcribe import _StubLLM as _NamingLLM

# ------------------------------------------------------------------------------ meter


def test_meter_prices_usage_nests_and_follows_thread_pools(settings) -> None:
    with spend.metering() as outer:
        with spend.metering() as inner:
            # diarized transcription: billed by tokens ($2.50 in / $10 out per 1M)
            spend.record(
                settings.diarize_model,
                SimpleNamespace(type="tokens", input_tokens=1_000_000, output_tokens=1_000_000),
            )
        assert inner.usd == pytest.approx(12.50)
        # chat usage shape, through a thread pool
        with ThreadPoolExecutor(2) as pool:
            spend.submit(
                pool,
                spend.record,
                settings.llm_model,
                {"prompt_tokens": 1_000_000, "completion_tokens": 2_000_000},
            ).result()
            pool.submit(spend.record, settings.llm_model, {"prompt_tokens": 5}).result()
        # duration-billed transcription
        spend.record(settings.text_transcribe_model, {"type": "duration", "seconds": 120})
        spend.record("unknown-model", {"prompt_tokens": 10})
    llm = settings.price_llm_input_per_mtok + 2 * settings.price_llm_output_per_mtok
    expected = 12.50 + llm + 2 * settings.price_text_transcribe_per_min
    assert outer.usd == pytest.approx(expected)  # the plain pool.submit call is not seen
    d = outer.to_dict()
    assert d["by_model"][settings.diarize_model]["output_tokens"] == 1_000_000
    assert d["by_model"]["unknown-model"]["usd"] == 0.0
    spend.record(settings.llm_model, {"prompt_tokens": 1})  # no meter open: ignored


def test_transcription_cost_is_measured_and_drives_the_estimate(
    session: Session, monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    ep = _seed_episode(session)
    assert ep.id is not None
    usage = {"type": "tokens", "input_tokens": 8_000, "output_tokens": 18_000}

    class _Transcriptions:
        def create(self, **_kw: Any) -> Any:
            segs = [{"speaker": "A", "start": 0.0, "end": 600.0, "text": "Ten minutes of talk."}]
            return SimpleNamespace(segments=segs, usage=usage)

    diarizer = OpenAIDiarizeTranscriber(
        model=settings.diarize_model,
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=_Transcriptions())),
    )

    def _one_chunk(_src: Path, workdir: Path, *_a: Any) -> list[audio.AudioChunk]:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "chunk_0000.mp3").write_bytes(b"x")
        return [audio.AudioChunk(path=workdir / "chunk_0000.mp3", offset=0.0, duration=600.0)]

    monkeypatch.setattr(audio, "prepare_chunks", _one_chunk)
    monkeypatch.setattr(transcribe, "get_transcriber", lambda: diarizer)
    monkeypatch.setattr(transcribe, "get_llm", lambda: _NamingLLM({"S1": "Host"}))
    monkeypatch.setattr(settings, "transcriber", "openai_diarize")

    # before any measured transcription the configured price is used
    assert transcription_rate(session) == (settings.price_diarize_per_min, False)

    transcribe.transcribe_episode(ep.id)

    session.expire_all()
    row = session.get(Episode, ep.id)
    assert row is not None and row.transcribe_cost is not None
    chunk_usd = 8_000 / 1e6 * 2.50 + 18_000 / 1e6 * 10.0  # = 0.2
    assert row.transcribe_cost["by_model"][settings.diarize_model]["usd"] == pytest.approx(
        chunk_usd
    )
    assert row.transcribe_cost["minutes"] == 10.0
    rate, measured = transcription_rate(session)
    assert measured and rate == pytest.approx(chunk_usd / 10.0)


# --------------------------------------------------------------------------- narrator


def _tr(speakers: dict[str, str], lines: list[tuple[str, str]]) -> Transcript:
    segs = [Segment(spk, i * 60.0, i * 60.0 + 55, text) for i, (spk, text) in enumerate(lines)]
    return Transcript(episode_id=1, model="m", speakers=speakers, segments=segs)


def test_host_is_named_in_the_podcast_title_or_asks_the_questions() -> None:
    lines = [("S1", "A teaser line from the guest."), ("S2", "Welcome. Why write it?")] * 3
    tr = _tr({"S1": "Robert Greene", "S2": "Andrew Huberman"}, lines)
    assert pipeline.host_label(tr, "Huberman Lab") == "S2"
    roles = pipeline.speaker_roles(tr, "Huberman Lab")
    assert roles[0] == ("S2", "Andrew Huberman", "host")
    assert roles[1] == ("S1", "Robert Greene", "guest")
    # no name in the title: the questioner hosts
    assert pipeline.host_label(tr, "The Daily Talk") == "S2"


def test_book_told_by_a_speaker_in_first_person(client, session) -> None:
    ep_id = _episode(session)
    est = client.post("/api/books/estimate", json={"episode_id": ep_id}).json()
    assert [(v["label"], v["role"]) for v in est["voices"]] == [("A", "host"), ("B", "guest")]

    bad = client.post("/api/books", json={"episode_id": ep_id, "narrator": "Z"})
    assert bad.status_code == 422

    created = client.post("/api/books", json={"episode_id": ep_id, "narrator": "A"})
    assert created.status_code == 201 and created.json()["narrator"] == "Host"
    book = _wait_ready(client, created.json()["id"])
    assert book["status"] == "ready", book["error"]
    row = session.get(Book, book["id"])
    assert row is not None and row.dir_path
    data = json.loads((storage.to_abs(row.dir_path) / "book.json").read_text())
    assert data["narrator"] == "Host"
    text = json.dumps(data["chapters"])
    assert "I pick up the thread" in text and "Guest picks up the thread" in text


def test_first_person_voice_reaches_writer_and_editor(session, monkeypatch, settings) -> None:
    ep_id = _episode(session)
    stub = _StubLLM()
    systems: list[str] = []
    real = stub.complete

    def _complete(messages, **kw):
        systems.append(messages[0]["content"])
        return real(messages, **kw)

    monkeypatch.setattr(stub, "complete", _complete)
    monkeypatch.setattr(pipeline, "get_llm", lambda: stub)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    book = Book(episode_id=ep_id, seed=5, narrator="Guest")
    session.add(book)
    session.commit()
    assert book.id is not None

    pipeline.build_book(book.id, on_progress=lambda f, m: None)

    plan, *sections = [s for s in systems if "fact-checking" not in s]
    editor = next(s for s in systems if "fact-checking" in s)
    for prompt in [" ".join(p.split()) for p in [plan, *sections]]:
        assert "Guest, the guest of this episode" in prompt
        assert "Everyone else (Host)" in prompt
    assert "first person as Guest" in " ".join(editor.split())
    assert "MAGAZINE FEATURE" not in plan


def test_first_person_narrator_words_are_not_turned_into_quotes() -> None:
    from app.books.document import Quote
    from app.books.verify import recover_hidden

    host = "long before I had a podcast I recommended it to students in my biology courses"
    guest = "people would come to me and say I do not know what my life task is at all"
    tr = _tr({"H": "Host", "G": "Guest"}, [("H", host), ("G", guest)])
    mine, theirs = f"I told him that {host}.", f"He answered that {guest}."

    def speakers(text: str, own: str = "") -> list[str]:
        return [r.speaker for r in recover_hidden(tr, [text], own) if isinstance(r, Quote)]

    # third-person narrator: both speakers' unquoted words become cited quotes
    assert speakers(mine) == ["Host"] and speakers(theirs) == ["Guest"]
    # told by the host: their own words stay narration, the guest's are still quoted
    assert speakers(mine, own="Host") == [] and speakers(theirs, own="Host") == ["Guest"]


# ------------------------------------------------------------------------ home page


def test_podcast_poster_is_a_cached_duotone_and_404_without_artwork(
    client, session, settings, monkeypatch
) -> None:
    from PIL import Image

    from app.models import Podcast

    pod = Podcast(
        title="Show", rss_url="https://x.test/feed", slug="show", image_url="https://x.test/a.jpg"
    )
    bare = Podcast(title="Bare", rss_url="https://x.test/bare", slug="bare")
    session.add_all([pod, bare])
    session.commit()
    monkeypatch.setattr(settings, "download_mode", "real")
    art = settings.podcasts_dir / "show" / "artwork.img"
    art.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 40), (200, 30, 30)).save(art, "JPEG")  # already on disk: no network

    first = client.get(f"/api/podcasts/{pod.id}/poster.png")
    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    cached = list(art.parent.glob("poster-*.png"))
    assert len(cached) == 1
    assert Image.open(cached[0]).size == (480, 480)
    assert client.get(f"/api/podcasts/{pod.id}/poster.png").content == first.content
    assert client.get(f"/api/podcasts/{bare.id}/poster.png").status_code == 404


def test_book_quote_comes_from_a_ready_book(client, session) -> None:
    assert client.get("/api/books/quote").json() is None
    ep_id = _episode(session)
    created = client.post("/api/books", json={"episode_id": ep_id}).json()
    _wait_ready(client, created["id"])
    row = session.get(Book, created["id"])
    assert row is not None and row.dir_path
    path = storage.to_abs(row.dir_path) / "book.json"
    data = json.loads(path.read_text())
    data["chapters"][0]["blocks"].append(
        {
            "t": "pull",
            "quote": {"text": "Morning light sets the clock", "speaker": "Guest", "start": 90.0},
        }
    )
    path.write_text(json.dumps(data))
    quote = client.get("/api/books/quote").json()
    assert quote["text"] == "Morning light sets the clock" and quote["speaker"] == "Guest"
    assert quote["episode_id"] == ep_id and quote["episode_number"] == 7
