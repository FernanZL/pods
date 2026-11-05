"""HTTP request/response models — THE API CONTRACT shared with the frontend.

CONTRACT FILE — do not modify; docs/architecture.md mirrors this file and
frontend/src/api/types.ts must match it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Step = Literal["download", "transcribe", "index"]
EpisodeStatus = Literal["new", "downloaded", "transcribed", "indexed"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
JobKind = Literal["process", "summarize", "reindex", "rebuild_index", "book"]


# --- Config ----------------------------------------------------------------


class Prices(BaseModel):
    transcription_per_min: float
    embedding_per_mtok: float
    llm_input_per_mtok: float
    llm_output_per_mtok: float


class AppConfigOut(BaseModel):
    llm_provider: str
    llm_model: str
    transcriber: str
    transcription_model: str
    embedding_model: str
    fake_mode: bool
    has_openai_key: bool
    has_openrouter_key: bool
    prices: Prices


# --- Podcasts --------------------------------------------------------------


class PodcastCreate(BaseModel):
    rss_url: str


class PodcastOut(BaseModel):
    id: int
    title: str
    rss_url: str
    description: str
    image_url: str | None
    episode_count: int
    indexed_count: int
    refreshed_at: datetime | None


# --- Episodes --------------------------------------------------------------


class EpisodeOut(BaseModel):
    id: int
    podcast_id: int
    podcast_title: str
    number: int
    title: str
    description: str  # plain text, HTML stripped, may be long
    published: datetime | None
    duration_seconds: int | None
    status: EpisodeStatus  # furthest completed step
    has_summary: bool
    speakers: dict[str, str]
    passage_count: int
    active_job_id: int | None  # queued/running job for this episode, if any


class EpisodeList(BaseModel):
    items: list[EpisodeOut]
    total: int  # total matching the filter (for pagination / "select all")


class SegmentOut(BaseModel):
    speaker: str  # label
    start: float
    end: float
    text: str


class CheckIssue(BaseModel):
    kind: str  # gap | coverage | loop | noise_speaker | one_speaker | speaker_share |
    #            names_fixed | names_doubt | empty
    severity: Literal["high", "medium", "low"]
    message: str
    at: float | None  # seconds, when the issue has a position


class TranscriptCheck(BaseModel):
    ok: bool
    issues: list[CheckIssue]
    names_checked: bool
    checked_at: str


class EpisodeDetail(EpisodeOut):
    audio_url: str  # original remote URL
    local_audio: bool
    downloaded_at: datetime | None
    transcribed_at: datetime | None
    indexed_at: datetime | None
    summarized_at: datetime | None  # True → GET /api/episodes/{id}/audio serves it
    segments: list[SegmentOut]  # [] until transcribed
    summary_markdown: str | None
    transcript_check: TranscriptCheck | None = None


class SelectionRequest(BaseModel):
    """Either explicit ids, or a filter ("select all matching")."""

    episode_ids: list[int] | None = None
    podcast_id: int | None = None
    q: str | None = None
    search_description: bool = False
    status: EpisodeStatus | None = None  # filter-based selection only
    steps: list[Step] = Field(default_factory=lambda: ["download", "transcribe", "index"])
    force: bool = False  # re-run steps even if already completed


class CostEstimate(BaseModel):
    episode_count: int
    known_minutes: float
    unknown_duration_count: int  # episodes whose duration the feed didn't give
    transcription_usd: float
    embedding_usd: float
    llm_usd: float  # speaker naming / attribution calls
    total_usd: float
    skipped_already_done: int  # episodes needing no paid work


# --- Jobs ------------------------------------------------------------------


class JobOut(BaseModel):
    id: int
    kind: JobKind
    episode_id: int | None
    episode_title: str | None
    steps: list[Step]
    status: JobStatus
    current_step: str | None
    progress: float
    message: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# --- Index -----------------------------------------------------------------


class IndexStats(BaseModel):
    podcasts: int
    episodes_total: int
    episodes_indexed: int
    passages: int
    embedding_model: str
    hours_indexed: float


# --- Chat ------------------------------------------------------------------


class Scope(BaseModel):
    """None/empty lists mean "no restriction" for that dimension."""

    podcast_ids: list[int] | None = None
    episode_ids: list[int] | None = None


class ChatRequest(BaseModel):
    conversation_id: int | None = None  # None → create a new conversation
    message: str
    scope: Scope = Field(default_factory=Scope)


class Citation(BaseModel):
    n: int  # the [n] marker used in the answer text
    episode_id: int
    episode_number: int = 0  # catalog number (Ep. 0213); 0 on messages saved before it existed
    episode_title: str
    podcast_title: str
    speaker: str  # display name
    start: float  # seconds
    end: float
    source: Literal["transcript", "summary"]
    snippet: str  # ≤ 300 chars of the passage


class MessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation]
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    title: str
    scope: Scope
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPatch(BaseModel):
    title: str | None = None
    scope: Scope | None = None


class EpisodeCitationRef(BaseModel):
    """A place where a conversation answer cited this episode (back-link)."""

    conversation_id: int
    conversation_title: str
    message_id: int
    n: int
    start: float
    end: float
    speaker: str
    created_at: datetime


# --- Discover (Apple Podcasts directory) -----------------------------------


class DiscoverPodcast(BaseModel):
    """A podcast found in the Apple Podcasts directory (not yet necessarily added)."""

    itunes_id: int
    title: str
    author: str
    feed_url: str | None  # None when Apple does not expose a public RSS feed
    artwork_url: str | None
    genre: str | None
    episode_count: int | None
    podcast_id: int | None  # set when this feed is already in the library


class DiscoverGenre(BaseModel):
    id: int
    name: str


# --- Books ---------------------------------------------------------------------


class BookCreate(BaseModel):
    episode_id: int


class BookEstimate(BaseModel):
    episode_id: int
    transcript_words: int
    chapters: int
    target_words: int
    est_pages: int
    llm_usd: float
    model: str


class BookOut(BaseModel):
    id: int
    episode_id: int
    episode_number: int
    episode_title: str
    podcast_title: str
    status: Literal["queued", "writing", "ready", "failed"]
    job_id: int | None
    progress: float  # 0..1 while writing
    message: str
    title: str
    seed: int
    family: str
    art: str
    chapters: int
    words: int
    pages: int
    quotes: int
    rejected_quotes: int
    review_issues: int
    review_fixed: int
    review_summary: str
    error: str | None
    created_at: datetime
    updated_at: datetime
