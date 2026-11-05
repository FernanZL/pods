"""Offline tests for transcription pipeline and transcription providers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session

from app import storage
from app.domain import ChatMessage, TranscriptionContext
from app.models import Episode, Podcast
from app.providers.transcription import base as tx_base
from app.providers.transcription.openai_diarize import OpenAIDiarizeTranscriber
from app.providers.transcription.openai_text_attrib import OpenAITextTranscriber
from app.services import audio, transcribe
from app.services.transcribe import transcribe_episode


class _StubLLM:
    model = "stub-llm"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> str:
        del messages, max_tokens, json_object
        return json.dumps(self._response)

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        del messages, max_tokens
        yield ""


def _seed_episode(session: Session) -> Episode:
    podcast = Podcast(
        title="Huberman Lab",
        rss_url="https://feeds.example.test/huberman.xml",
        slug="huberman-lab",
    )
    session.add(podcast)
    session.flush()
    assert podcast.id is not None
    ep = Episode(
        podcast_id=podcast.id,
        guid="ep-tx-1",
        number=1,
        title="Sleep & Dopamine with Dr. Jane Doe",
        slug="0001-sleep-dopamine",
        description="Interview with Dr. Jane Doe.",
        audio_url="https://cdn.example.test/ep1.mp3",
    )
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return ep


def test_transcribe_episode_fake_mode_skips_ffmpeg(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ep = _seed_episode(session)
    assert ep.id is not None

    def _forbid_ffmpeg(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("ffmpeg prepare_chunks must not be called in fake transcriber mode")

    monkeypatch.setattr(audio, "prepare_chunks", _forbid_ffmpeg)
    monkeypatch.setattr(
        transcribe,
        "get_llm",
        lambda: _StubLLM({"S1": "Andrew Huberman", "S2": "Dr. Jane Doe"}),
    )

    result = transcribe_episode(ep.id)
    assert len(result.segments) == 4
    assert result.speakers == {"S1": "Andrew Huberman", "S2": "Dr. Jane Doe"}
    assert "audio.mp3" in result.segments[0].text

    session.expire_all()
    db_ep = session.get(Episode, ep.id)
    assert db_ep is not None
    assert db_ep.transcribed_at is not None
    assert db_ep.transcript_path is not None

    json_path = storage.to_abs(db_ep.transcript_path)
    assert json_path.is_file()
    assert json_path.with_suffix(".md").is_file()
    assert not (json_path.parent / "work").exists()

    cached = transcribe_episode(ep.id, force=False)
    assert cached.speakers == result.speakers


def test_transcribe_episode_diarize_passes_known_speakers_and_applies_offsets(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ep = _seed_episode(session)
    assert ep.id is not None

    recorded_calls: list[dict[str, Any]] = []

    class _FakeTranscriptions:
        def create(self, **kwargs: Any) -> Any:
            recorded_calls.append(kwargs)
            call_no = len(recorded_calls)
            if call_no == 1:
                return SimpleNamespace(
                    segments=[
                        {
                            "speaker": "A",
                            "start": 0.0,
                            "end": 4.0,
                            "text": "Welcome back.",
                        },
                        {
                            "speaker": "A",
                            "start": 4.8,
                            "end": 9.0,
                            "text": "Today we discuss sleep.",
                        },
                        {
                            "speaker": "B",
                            "start": 10.0,
                            "end": 11.0,
                            "text": "Happy to be here.",
                        },
                        {
                            "speaker": None,
                            "start": 11.0,
                            "end": 12.0,
                            "text": "[music]",
                        },
                    ]
                )
            return SimpleNamespace(
                segments=[
                    {"speaker": "S1", "start": 0.5, "end": 5.0, "text": "Second chunk question."},
                    {"speaker": "S2", "start": 6.0, "end": 12.5, "text": "Second chunk answer."},
                ]
            )

    fake_client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_FakeTranscriptions()))
    diarizer = OpenAIDiarizeTranscriber(
        api_key="unused",
        model="gpt-4o-transcribe-diarize",
        client=fake_client,
    )

    def _fake_prepare_chunks(
        _src: Path,
        workdir: Path,
        _chunk_seconds: int | None = None,
        _bitrate_kbps: int | None = None,
    ) -> list[audio.AudioChunk]:
        workdir.mkdir(parents=True, exist_ok=True)
        c0 = workdir / "chunk_0000.mp3"
        c1 = workdir / "chunk_0001.mp3"
        c0.write_bytes(b"chunk0")
        c1.write_bytes(b"chunk1")
        return [
            audio.AudioChunk(path=c0, offset=0.0, duration=600.0),
            audio.AudioChunk(path=c1, offset=600.0, duration=600.0),
        ]

    clip_requests: list[tuple[float, float, Path]] = []

    def _fake_cut_clip(_src: Path, start: float, end: float, dst: Path) -> Path:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(f"ref-{dst.stem}".encode())
        clip_requests.append((start, end, dst))
        return dst

    monkeypatch.setattr(audio, "prepare_chunks", _fake_prepare_chunks)
    monkeypatch.setattr(audio, "cut_clip", _fake_cut_clip)
    monkeypatch.setattr(transcribe, "get_transcriber", lambda: diarizer)
    monkeypatch.setattr(
        transcribe,
        "get_llm",
        lambda: _StubLLM({"S1": "Andrew Huberman", "S2": "unknown"}),
    )

    result = transcribe_episode(ep.id)

    assert len(recorded_calls) == 2
    assert "known_speaker_names" not in recorded_calls[0]
    assert "known_speaker_references" not in recorded_calls[0]

    assert recorded_calls[1]["known_speaker_names"] == ["S1", "S2"]
    refs = recorded_calls[1]["known_speaker_references"]
    assert len(refs) == 2
    assert all(r.startswith("data:audio/mpeg;base64,") for r in refs)

    # Speaker B's 1.0s segment is clamped to the 2.0s minimum clip length
    assert clip_requests[0][:2] == (4.8, 9.0)
    assert clip_requests[1][:2] == (10.0, 12.0)

    # Chunk 1's two consecutive A segments (gap 0.8s < 1.5s) are merged; chunk 2 has +600s offset
    assert len(result.segments) == 4
    assert result.segments[0].speaker == "S1"
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 9.0
    assert result.segments[0].text == "Welcome back. Today we discuss sleep."

    assert result.segments[2].speaker == "S1"
    assert result.segments[2].start == pytest.approx(600.5)
    assert result.segments[3].speaker == "S2"
    assert result.segments[3].start == pytest.approx(606.0)
    assert result.speakers == {"S1": "Andrew Huberman", "S2": "Speaker 2"}


def test_diarize_retry_and_text_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"mp3data")

    delays: list[float] = []
    monkeypatch.setattr(tx_base.time, "sleep", lambda d: delays.append(d))

    attempts = 0

    class _FlakyTranscriptions:
        def create(self, **_kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("transient gateway failure")
            return {"segments": [{"speaker": "A", "start": 0.0, "end": 2.0, "text": "Recovered."}]}

    flaky_client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_FlakyTranscriptions()))
    diarizer = OpenAIDiarizeTranscriber(client=flaky_client)
    ctx = TranscriptionContext(
        episode_id=1,
        title="Ep",
        description="",
        podcast_title="Pod",
    )
    segs = diarizer.transcribe_chunk(audio_file, known_speakers=[], context=ctx)
    assert attempts == 3
    assert len(delays) == 2
    assert delays[1] == pytest.approx(delays[0] * 2)
    assert len(segs) == 1 and segs[0].text == "Recovered."

    text_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=lambda **_kw: SimpleNamespace(text="Hello there. Glad to join.")
            )
        )
    )
    turn_llm = _StubLLM(
        {
            "turns": [
                {"speaker": "A", "text": "Hello there."},
                {"speaker": "B", "text": "Glad to join."},
            ]
        }
    )
    text_tx = OpenAITextTranscriber(llm=turn_llm, client=text_client)
    attributed = text_tx.transcribe_chunk(audio_file, known_speakers=[], context=ctx)
    assert len(attributed) == 2
    assert attributed[0].speaker == "A"
    assert attributed[1].speaker == "B"
    assert attributed[0].start == 0.0
    assert attributed[1].end >= attributed[0].end > 0.0


def test_later_chunks_run_in_parallel_and_reassemble_in_order(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunks after the first are sent concurrently; out-of-order completions are re-sorted."""
    import threading
    import time as _time

    ep = _seed_episode(session)
    assert ep.id is not None

    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0
    calls: list[dict[str, Any]] = []

    class _SlowTranscriptions:
        def create(self, **kwargs: Any) -> Any:
            nonlocal in_flight, max_in_flight
            name = Path(kwargs["file"].name).name
            idx = int(name.split("_")[1].split(".")[0])
            with lock:
                calls.append(kwargs)
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            # later chunks finish first, to force out-of-order completion
            _time.sleep(0.05 * (5 - idx) if idx else 0.01)
            with lock:
                in_flight -= 1
            speaker = "A" if idx == 0 else "S1"
            return SimpleNamespace(
                segments=[{"speaker": speaker, "start": 1.0, "end": 2.0, "text": f"chunk {idx}"}]
            )

    diarizer = OpenAIDiarizeTranscriber(
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=_SlowTranscriptions()))
    )

    def _chunks(_src: Path, workdir: Path, *_a: Any) -> list[audio.AudioChunk]:
        workdir.mkdir(parents=True, exist_ok=True)
        out = []
        for i in range(5):
            p = workdir / f"chunk_{i:04d}.mp3"
            p.write_bytes(b"x")
            out.append(audio.AudioChunk(path=p, offset=600.0 * i, duration=600.0))
        return out

    def _clip(_src: Path, _s: float, _e: float, dst: Path) -> Path:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"ref")
        return dst

    monkeypatch.setattr(audio, "prepare_chunks", _chunks)
    monkeypatch.setattr(audio, "cut_clip", _clip)
    monkeypatch.setattr(transcribe, "get_transcriber", lambda: diarizer)
    monkeypatch.setattr(transcribe, "get_llm", lambda: _StubLLM({"S1": "Host"}))

    result = transcribe_episode(ep.id)

    assert len(calls) == 5
    assert max_in_flight > 1  # chunks 2..5 overlapped
    assert all(c.get("known_speaker_names") == ["S1"] for c in calls[1:])
    # reassembled in time order with chunk offsets applied, despite reversed completion
    assert [seg.text for seg in result.segments] == [f"chunk {i}" for i in range(5)]
    assert [seg.start for seg in result.segments] == pytest.approx(
        [1.0 + 600.0 * i for i in range(5)]
    )
