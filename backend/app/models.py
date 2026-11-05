"""SQLModel tables persisted in data/app.db.

CONTRACT FILE — do not modify without updating docs/architecture.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Podcast(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    rss_url: str = Field(index=True, unique=True)
    slug: str = Field(index=True, unique=True)
    description: str = ""
    image_url: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    refreshed_at: datetime | None = None


class Episode(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("podcast_id", "guid"),)

    id: int | None = Field(default=None, primary_key=True)
    podcast_id: int = Field(foreign_key="podcast.id", index=True)
    guid: str  # RSS guid, falls back to audio_url
    number: int  # position in the feed, oldest = 1 (stable as feed grows)
    title: str
    slug: str  # f"{number:04d}-{sanitized title}" — folder name on disk
    description: str = ""
    published: datetime | None = None
    audio_url: str
    duration_seconds: int | None = None

    # Pipeline state. A timestamp set == step completed. Paths are relative to
    # Settings.data_dir.
    audio_path: str | None = None
    downloaded_at: datetime | None = None
    transcript_path: str | None = None
    transcribed_at: datetime | None = None
    speakers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    indexed_at: datetime | None = None
    passage_count: int = 0
    summary_path: str | None = None
    summarized_at: datetime | None = None
    # Transcript health check (see services/transcript_check.py): {"ok", "issues", ...}
    transcript_check: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # "process" (steps from `steps`), "summarize", "reindex", "rebuild_index"
    kind: str = Field(index=True)
    episode_id: int | None = Field(default=None, foreign_key="episode.id", index=True)
    steps: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    force: bool = False
    # queued | running | done | failed | cancelled
    status: str = Field(default="queued", index=True)
    current_step: str | None = None
    progress: float = 0.0  # 0..1 within current_step
    message: str = ""
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = "New conversation"
    # Scope JSON: {"podcast_ids": [..] | null, "episode_ids": [..] | null}
    scope: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    # list[Citation-as-dict] (see schemas.Citation); empty for user messages
    citations: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Book(SQLModel, table=True):
    """A long-form PDF book written from one episode.

    The text (book.json) is generated once; the design is a seeded theme, so
    "reshuffle" re-renders the PDF with a new seed without any model calls.
    """

    id: int | None = Field(default=None, primary_key=True)
    episode_id: int = Field(foreign_key="episode.id", index=True)
    job_id: int | None = Field(default=None, index=True)  # the job writing it
    status: str = Field(default="queued", index=True)  # queued | writing | ready | failed
    seed: int
    title: str = ""
    family: str = ""  # colour family of the current design
    art: str = ""  # cover art kind of the current design
    chapters: int = 0
    words: int = 0
    pages: int = 0
    quotes: int = 0  # verified quotes in the book
    rejected_quotes: int = 0  # writer quotes that failed verification (kept as narrative)
    review_issues: int = 0  # problems the editor found in the narration
    review_fixed: int = 0  # ...of which were fixed by rewriting the section
    review_summary: str = ""
    dir_path: str | None = None  # relative to data_dir
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
