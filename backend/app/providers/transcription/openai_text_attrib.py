"""OpenAI plain-text transcription + LLM speaker turn attribution backend."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.domain import ChatMessage, KnownSpeaker, LLMClient, Segment, TranscriptionContext
from app.providers import get_llm
from app.providers.transcription.base import get_field, with_retry
from app.services import audio


class OpenAITextTranscriber:
    """Transcribes audio as text and attributes speaker turns via an LLM call."""

    name: str
    supports_diarization: bool

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-transcribe",
        llm: LLMClient | None = None,
        client: Any | None = None,
        timeout: float = 900.0,
    ) -> None:
        self.name = model
        self.supports_diarization = False
        self._llm = llm
        self._client = (
            client
            if client is not None
            else OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        )

    def _chunk_duration(self, audio_path: Path, text: str) -> float:
        with suppress(OSError, RuntimeError, ValueError):
            dur = audio.probe_duration(audio_path)
            if dur > 0:
                return dur
        return max(1.0, len(text.split()) / 2.5)

    def _attribute_turns(
        self,
        text: str,
        context: TranscriptionContext,
    ) -> list[tuple[str, str]]:
        llm = self._llm if self._llm is not None else get_llm()
        messages: list[ChatMessage] = [
            {
                "role": "system",
                "content": (
                    "Split the podcast transcript into speaker turns using short labels "
                    '("A", "B", ...). Return JSON: {"turns": [{"speaker": "A", "text": "..."}]}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Podcast: {context.podcast_title}\n"
                    f"Episode: {context.title}\n\n"
                    f"Transcript:\n{text}"
                ),
            },
        ]
        raw = llm.complete(messages, json_object=True)
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None

        items: list[Any] = []
        if isinstance(parsed, dict):
            cand = parsed.get("turns") or parsed.get("segments")
            if isinstance(cand, list):
                items = cand
        elif isinstance(parsed, list):
            items = parsed

        turns: list[tuple[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            spk = str(item.get("speaker") or "A").strip() or "A"
            turn_text = str(item.get("text") or "").strip()
            if turn_text:
                turns.append((spk, turn_text))

        if not turns:
            turns = [("A", text.strip())]
        return turns

    def transcribe_chunk(
        self,
        audio_path: Path,
        *,
        known_speakers: list[KnownSpeaker],
        context: TranscriptionContext,
    ) -> list[Segment]:
        """Transcribe plain text and interpolate turn timestamps by char length."""
        del known_speakers  # plain-text backend does not accept audio references

        def _call() -> Any:
            with audio_path.open("rb") as audio_file:
                return self._client.audio.transcriptions.create(
                    model=self.name,
                    file=audio_file,
                )

        resp = with_retry(_call)
        text = resp if isinstance(resp, str) else str(get_field(resp, "text", "") or "")
        cleaned = text.strip()
        if not cleaned:
            return []

        duration = self._chunk_duration(audio_path, cleaned)
        turns = self._attribute_turns(cleaned, context)
        total_chars = sum(len(t) for _, t in turns) or 1

        segments: list[Segment] = []
        cursor = 0
        for speaker, turn_text in turns:
            start = round((cursor / total_chars) * duration, 2)
            cursor += len(turn_text)
            end = round((cursor / total_chars) * duration, 2)
            segments.append(
                Segment(
                    speaker=speaker,
                    start=start,
                    end=max(start, end),
                    text=turn_text,
                )
            )
        return segments
