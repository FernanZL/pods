"""Core domain types and provider/service protocols.

CONTRACT FILE — every module codes against these. Do not modify; if a
change seems necessary, report it instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """One diarized utterance. Times are seconds from the start of the
    *episode* (services add chunk offsets; backends return chunk-relative)."""

    speaker: str  # stable label, e.g. "A", "B" (or a known speaker name)
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    """Persisted as transcript.json next to the audio file.

    JSON shape:
      {"episode_id": 1, "model": "gpt-4o-transcribe-diarize",
       "speakers": {"A": "Andrew Huberman", "B": "Guest name"},
       "segments": [{"speaker": "A", "start": 0.0, "end": 4.2, "text": "..."}]}
    """

    episode_id: int
    model: str
    speakers: dict[str, str]  # label -> display name ("Speaker A" if unknown)
    segments: list[Segment]


@dataclass
class KnownSpeaker:
    """Reference clip passed to diarization so labels stay consistent across
    chunks. ``reference_path`` is a 2–10 s audio clip."""

    name: str
    reference_path: Path


@dataclass
class TranscriptionContext:
    episode_id: int
    title: str
    description: str
    podcast_title: str


# progress callback: fraction 0..1 and a short human message
ProgressFn = Callable[[float, str], None]


@runtime_checkable
class Transcriber(Protocol):
    """Transcribes ONE audio chunk (≤ 25 MB). Chunking, offsets, reference
    clips and speaker naming live in services/transcribe.py."""

    name: str  # model id recorded in Transcript.model
    supports_diarization: bool

    def transcribe_chunk(
        self,
        audio_path: Path,
        *,
        known_speakers: list[KnownSpeaker],
        context: TranscriptionContext,
    ) -> list[Segment]:
        """Return segments with times relative to the chunk start."""
        ...


# ---------------------------------------------------------------------------
# LLM + embeddings
# ---------------------------------------------------------------------------

ChatMessage = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


@runtime_checkable
class LLMClient(Protocol):
    model: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> str:
        """Single non-streamed completion. ``json_object`` requests
        response_format={"type": "json_object"}."""
        ...

    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int | None = None
    ) -> Iterator[str]:
        """Yield text deltas."""
        ...


@runtime_checkable
class Embedder(Protocol):
    id: str  # == Settings.embedding_id
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed. Implementations batch internally (≤ 256 per call)."""
        ...


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------

PassageSource = Literal["transcript", "summary"]


@dataclass
class Passage:
    """A retrievable chunk. ``id`` is deterministic: f"ep{episode_id}:{source}:{n}".

    metadata keys (all scalar, Chroma-compatible):
      podcast_id:int, episode_id:int, episode_title:str, podcast_title:str,
      published:str (ISO or ""), speaker:str, start:float, end:float,
      source:"transcript"|"summary", chunk_no:int
    """

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredPassage:
    passage: Passage
    distance: float


class VectorStore(Protocol):
    def upsert(self, passages: list[Passage], embeddings: list[list[float]]) -> None: ...

    def delete_episode(self, episode_id: int) -> int:
        """Remove all passages of an episode; return number removed."""
        ...

    def query(
        self, embedding: list[float], *, k: int, where: dict[str, Any] | None = None
    ) -> list[ScoredPassage]: ...

    def count(self) -> int: ...

    def episode_ids(self) -> set[int]: ...
