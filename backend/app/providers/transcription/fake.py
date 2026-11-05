"""Deterministic offline fake transcription backend for tests and demo mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domain import KnownSpeaker, Segment, TranscriptionContext


class FakeTranscriber:
    """Offline transcriber producing deterministic alternating A/B utterances."""

    name: str
    supports_diarization: bool

    def __init__(self, client: Any | None = None) -> None:
        self.name = "fake-transcriber"
        self.supports_diarization = True
        self._client = client

    def transcribe_chunk(
        self,
        audio_path: Path,
        *,
        known_speakers: list[KnownSpeaker],
        context: TranscriptionContext,
    ) -> list[Segment]:
        """Generate deterministic segments referencing the file name and size."""
        del known_speakers
        size = audio_path.stat().st_size if audio_path.exists() else 0
        fname = audio_path.name
        return [
            Segment(
                speaker="A",
                start=0.0,
                end=15.0,
                text=(
                    f"Lorem ipsum dolor sit amet in {fname} ({size} bytes), "
                    f"introducing {context.title}."
                ),
            ),
            Segment(
                speaker="B",
                start=15.0,
                end=30.0,
                text=(
                    f"Consectetur adipiscing elit from {fname}, exploring key "
                    "mechanisms, evidence, and practical protocols."
                ),
            ),
            Segment(
                speaker="A",
                start=30.0,
                end=45.0,
                text=(
                    f"Sed do eiusmod tempor incididunt ut labore et dolore magna "
                    f"aliqua recorded in {fname}."
                ),
            ),
            Segment(
                speaker="B",
                start=45.0,
                end=60.0,
                text=(
                    f"Ut enim ad minim veniam quis nostrud exercitation ullamco "
                    f"laboris nisi ut aliquip ex {fname}."
                ),
            ),
        ]
