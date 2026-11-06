"""OpenAI native speaker-diarization transcription backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

from app import spend
from app.domain import KnownSpeaker, Segment, TranscriptionContext
from app.providers.transcription.base import encode_audio_data_url, get_field, with_retry


class OpenAIDiarizeTranscriber:
    """Transcribes audio chunks using OpenAI's diarized_json format."""

    name: str
    supports_diarization: bool

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-transcribe-diarize",
        client: Any | None = None,
        timeout: float = 900.0,
    ) -> None:
        self.name = model
        self.supports_diarization = True
        self._client = (
            client
            if client is not None
            else OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        )

    def transcribe_chunk(
        self,
        audio_path: Path,
        *,
        known_speakers: list[KnownSpeaker],
        context: TranscriptionContext,
    ) -> list[Segment]:
        """Transcribe one audio chunk and return chunk-relative diarized segments."""
        del context  # metadata is used later for LLM speaker naming
        kwargs: dict[str, Any] = {
            "model": self.name,
            "response_format": "diarized_json",
            "chunking_strategy": "auto",
        }
        if known_speakers:
            kwargs["known_speaker_names"] = [ks.name for ks in known_speakers]
            kwargs["known_speaker_references"] = [
                encode_audio_data_url(ks.reference_path) for ks in known_speakers
            ]

        def _call() -> Any:
            with audio_path.open("rb") as audio_file:
                return self._client.audio.transcriptions.create(file=audio_file, **kwargs)

        resp = with_retry(_call)
        spend.record(self.name, get_field(resp, "usage"))
        raw_segments = get_field(resp, "segments", []) or []

        segments: list[Segment] = []
        for item in raw_segments:
            speaker = get_field(item, "speaker")
            if not speaker:
                continue
            text = str(get_field(item, "text", "") or "").strip()
            if not text:
                continue
            start = float(get_field(item, "start", 0.0) or 0.0)
            end = float(get_field(item, "end", start) or start)
            segments.append(
                Segment(
                    speaker=str(speaker),
                    start=start,
                    end=max(start, end),
                    text=text,
                )
            )
        return segments
