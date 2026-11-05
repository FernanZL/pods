"""Episode summarization service ported from legacy notebook cell 24."""

from __future__ import annotations

from pathlib import Path

from app import db, storage
from app.config import get_settings
from app.domain import ChatMessage, ProgressFn
from app.models import Episode, Podcast, utcnow
from app.providers import get_llm
from app.services import indexing

SUMMARY_SYSTEM_PROMPT = (
    "You are an assistant that summarizes podcast episodes in a detailed and exhaustive manner, "
    "extracting all key points, topics discussed, insights, and notable quotes, "
    "in structured markdown format."
)


def _noop_progress(_fraction: float, _message: str) -> None:
    """Default no-op progress callback."""


def build_summary_user_prompt(transcript_markdown: str) -> str:
    """Build the user prompt ported from notebook 1 cell 24."""
    return (
        "Below is the transcript of a podcast episode.\n"
        "Please write an exhaustive and detailed summary in markdown, including:\n"
        "- A full overview of the episode\n"
        "- All key topics discussed\n"
        "- Important insights or conclusions\n"
        "- Notable quotes\n"
        "- Any actionable ideas or takeaways\n\n"
        "Transcript:\n"
        f"{transcript_markdown}"
    )


def _load_speaker_labelled_transcript(
    transcript_json_path: Path,
    speakers: dict[str, str],
) -> str:
    md_path = transcript_json_path.with_suffix(".md")
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")

    if not transcript_json_path.exists():
        raise FileNotFoundError(f"Transcript file not found: {transcript_json_path}")

    transcript = storage.read_transcript(transcript_json_path)
    merged_speakers = {**transcript.speakers, **speakers}
    lines: list[str] = []
    for seg in transcript.segments:
        name = merged_speakers.get(seg.speaker, f"Speaker {seg.speaker}")
        lines.append(f"**{name}** [{storage.fmt_ts(seg.start)}] {seg.text.strip()}")
    return "\n\n".join(lines) + "\n"


def summarize_episode(
    episode_id: int,
    on_progress: ProgressFn = _noop_progress,
    force: bool = False,
) -> Path:
    """Generate ``summary.md`` for an episode, update DB state, and index the summary."""
    on_progress(0.0, "Checking episode state")

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is None:
            raise ValueError(f"Episode {episode_id} not found")

        if not force and ep.summary_path:
            existing = storage.to_abs(ep.summary_path)
            if existing.exists():
                on_progress(1.0, "Summary already exists")
                return existing

        if not ep.transcript_path:
            raise ValueError(f"Episode {episode_id} must be transcribed before summarizing")

        podcast = session.get(Podcast, ep.podcast_id)
        transcript_json_path = storage.to_abs(ep.transcript_path)
        ep_dir = (
            storage.episode_dir(podcast, ep) if podcast is not None else transcript_json_path.parent
        )
        ep_speakers = dict(ep.speakers or {})

    transcript_md = _load_speaker_labelled_transcript(transcript_json_path, ep_speakers)
    messages: list[ChatMessage] = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": build_summary_user_prompt(transcript_md)},
    ]

    on_progress(0.2, "Generating markdown summary")
    settings = get_settings()
    summary_markdown = get_llm().complete(messages, max_tokens=settings.summary_max_tokens)

    ep_dir.mkdir(parents=True, exist_ok=True)
    summary_file = ep_dir / "summary.md"
    summary_file.write_text(summary_markdown, encoding="utf-8")
    rel_summary = storage.to_rel(summary_file)

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.summary_path = rel_summary
            ep.summarized_at = utcnow()
            session.add(ep)
            session.commit()

    on_progress(0.85, "Indexing summary")
    indexing.index_summary(episode_id)
    on_progress(1.0, "Summary complete")
    return summary_file
