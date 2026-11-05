"""Transcript and summary chunking and Chroma vector indexing services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import select

from app import db, storage
from app.config import get_settings
from app.domain import Passage, ProgressFn, Transcript, VectorStore
from app.models import Episode, Podcast, utcnow
from app.providers import get_embedder
from app.services.vectorstore import ChromaVectorStore, get_vector_store


def _noop_progress(_fraction: float, _message: str) -> None:
    """Default no-op progress callback."""


@dataclass
class _Unit:
    seg_idx: int
    speaker_name: str
    raw_text: str
    start: float
    end: float


def _speaker_display(speakers: dict[str, str], label: str) -> str:
    if label in speakers:
        return speakers[label]
    if len(label) == 1 and label.isalpha():
        return f"Speaker {label}"
    return label or "Unknown"


def _split_text_pieces(text: str, max_piece_chars: int) -> list[str]:
    """Split text along word boundaries into pieces of at most ``max_piece_chars``."""
    limit = max(1, max_piece_chars)
    words = text.split()
    if not words:
        return []

    pieces: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        if len(word) > limit:
            if current:
                pieces.append(" ".join(current))
                current = []
                current_len = 0
            for pos in range(0, len(word), limit):
                pieces.append(word[pos : pos + limit])
            continue

        added = len(word) if not current else len(word) + 1
        if current and current_len + added > limit:
            pieces.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += added

    if current:
        pieces.append(" ".join(current))
    return pieces


def _render_units(units: list[_Unit]) -> str:
    """Render units to chunk text, grouping sub-units from the same segment."""
    lines: list[str] = []
    idx = 0
    total = len(units)
    while idx < total:
        seg_idx = units[idx].seg_idx
        speaker = units[idx].speaker_name
        parts = [units[idx].raw_text]
        idx += 1
        while idx < total and units[idx].seg_idx == seg_idx:
            parts.append(units[idx].raw_text)
            idx += 1
        lines.append(f"{speaker}: {' '.join(parts)}")
    return "\n".join(lines)


def _dominant_speaker(units: list[_Unit]) -> str:
    """Return the speaker with the most text characters (ties go to first speaker)."""
    totals: dict[str, int] = {}
    order: list[str] = []
    for unit in units:
        if unit.speaker_name not in totals:
            totals[unit.speaker_name] = 0
            order.append(unit.speaker_name)
        totals[unit.speaker_name] += len(unit.raw_text)
    return max(order, key=lambda name: totals[name])


def chunk_transcript(
    transcript: Transcript,
    chunk_chars: int | None = None,
    chunk_overlap_chars: int | None = None,
    *,
    podcast_id: int = 0,
    episode_title: str = "",
    podcast_title: str = "",
    published: str = "",
) -> list[Passage]:
    """Chunk a diarized ``Transcript`` into retrievable ``Passage`` items."""
    settings = get_settings()
    max_chars = max(40, chunk_chars if chunk_chars is not None else settings.chunk_chars)
    raw_overlap = (
        chunk_overlap_chars if chunk_overlap_chars is not None else settings.chunk_overlap_chars
    )
    overlap_chars = max(0, min(raw_overlap, max_chars - 1))

    units: list[_Unit] = []
    for seg_idx, seg in enumerate(transcript.segments):
        cleaned = seg.text.strip()
        if not cleaned:
            continue
        speaker_name = _speaker_display(transcript.speakers, seg.speaker)
        prefix_len = len(speaker_name) + 2
        if prefix_len + len(cleaned) <= max_chars:
            units.append(
                _Unit(
                    seg_idx=seg_idx,
                    speaker_name=speaker_name,
                    raw_text=cleaned,
                    start=float(seg.start),
                    end=float(seg.end),
                )
            )
        else:
            avail = max(1, max_chars - prefix_len)
            sub_target = min(avail, max(20, overlap_chars if overlap_chars > 0 else avail // 2))
            pieces = _split_text_pieces(cleaned, sub_target)
            duration = max(0.0, float(seg.end) - float(seg.start))
            total_chars = max(1, sum(len(p) for p in pieces))
            cursor = 0
            for piece in pieces:
                frac_start = cursor / total_chars
                cursor += len(piece)
                frac_end = cursor / total_chars
                units.append(
                    _Unit(
                        seg_idx=seg_idx,
                        speaker_name=speaker_name,
                        raw_text=piece,
                        start=round(float(seg.start) + duration * frac_start, 2),
                        end=round(float(seg.start) + duration * frac_end, 2),
                    )
                )

    if not units:
        return []

    passages: list[Passage] = []
    idx = 0
    num_units = len(units)
    min_turn_chars = max(overlap_chars + 1, max_chars // 2)

    while idx < num_units:
        end_idx = idx + 1
        while end_idx < num_units and len(_render_units(units[idx : end_idx + 1])) <= max_chars:
            end_idx += 1

        if end_idx < num_units and units[end_idx - 1].speaker_name == units[end_idx].speaker_name:
            for boundary in range(end_idx - 1, idx, -1):
                if (
                    units[boundary - 1].speaker_name != units[boundary].speaker_name
                    and len(_render_units(units[idx:boundary])) >= min_turn_chars
                ):
                    end_idx = boundary
                    break

        chunk_units = units[idx:end_idx]
        chunk_no = len(passages)
        metadata: dict[str, Any] = {
            "podcast_id": int(podcast_id),
            "episode_id": int(transcript.episode_id),
            "episode_title": episode_title,
            "podcast_title": podcast_title,
            "published": published,
            "speaker": _dominant_speaker(chunk_units),
            "start": float(chunk_units[0].start),
            "end": float(chunk_units[-1].end),
            "source": "transcript",
            "chunk_no": chunk_no,
        }
        passages.append(
            Passage(
                id=f"ep{transcript.episode_id}:transcript:{chunk_no}",
                text=_render_units(chunk_units),
                metadata=metadata,
            )
        )

        if end_idx >= num_units:
            break

        next_idx = end_idx
        if overlap_chars > 0:
            while next_idx > idx + 1:
                cand_len = len(_render_units(units[next_idx - 1 : end_idx]))
                if cand_len <= overlap_chars:
                    next_idx -= 1
                elif (
                    next_idx == end_idx
                    and units[end_idx - 1].speaker_name == units[end_idx].speaker_name
                    and cand_len <= max_chars // 2
                ):
                    next_idx -= 1
                    break
                else:
                    break
        idx = next_idx

    return passages


def _chunk_markdown_summary(
    summary_text: str,
    *,
    episode_id: int,
    podcast_id: int,
    episode_title: str,
    podcast_title: str,
    published: str,
) -> list[Passage]:
    """Chunk markdown summary text into ``Passage`` items with ``source='summary'``."""
    cleaned = summary_text.strip()
    if not cleaned:
        return []

    settings = get_settings()
    max_chars = max(40, settings.chunk_chars)
    overlap_chars = max(0, min(settings.chunk_overlap_chars, max_chars - 1))

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    blocks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            blocks.append(para)
        else:
            blocks.extend(_split_text_pieces(para, max(20, overlap_chars or max_chars // 2)))

    passages: list[Passage] = []
    idx = 0
    total = len(blocks)
    while idx < total:
        end_idx = idx + 1
        while end_idx < total and len("\n\n".join(blocks[idx : end_idx + 1])) <= max_chars:
            end_idx += 1

        chunk_no = len(passages)
        passages.append(
            Passage(
                id=f"ep{episode_id}:summary:{chunk_no}",
                text="\n\n".join(blocks[idx:end_idx]),
                metadata={
                    "podcast_id": int(podcast_id),
                    "episode_id": int(episode_id),
                    "episode_title": episode_title,
                    "podcast_title": podcast_title,
                    "published": published,
                    "speaker": "",
                    "start": 0.0,
                    "end": 0.0,
                    "source": "summary",
                    "chunk_no": chunk_no,
                },
            )
        )
        if end_idx >= total:
            break

        next_idx = end_idx
        if overlap_chars > 0:
            while next_idx > idx + 1:
                if len("\n\n".join(blocks[next_idx - 1 : end_idx])) <= overlap_chars:
                    next_idx -= 1
                else:
                    break
        idx = next_idx

    return passages


def _delete_source(store: VectorStore, episode_id: int, source: str) -> None:
    if isinstance(store, ChromaVectorStore):
        store.delete_episode_source(episode_id, source)
    elif source == "transcript":
        store.delete_episode(episode_id)


def _episode_total_passages(store: VectorStore, episode_id: int, fallback: int) -> int:
    if isinstance(store, ChromaVectorStore):
        return store.count_episode(episode_id)
    return fallback


def index_episode(
    episode_id: int,
    on_progress: ProgressFn = _noop_progress,
    force: bool = False,
) -> int:
    """Chunk, embed, and upsert an episode's transcript into the vector store."""
    on_progress(0.0, "Loading episode transcript")
    store = get_vector_store()

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is None:
            raise ValueError(f"Episode {episode_id} not found")
        if not force and ep.indexed_at is not None and episode_id in store.episode_ids():
            on_progress(1.0, "Already indexed")
            return ep.passage_count
        if not ep.transcript_path:
            raise ValueError(f"Episode {episode_id} has no transcript_path")

        transcript_file = storage.to_abs(ep.transcript_path)
        if not transcript_file.exists():
            raise FileNotFoundError(f"Transcript file missing: {transcript_file}")

        podcast = session.get(Podcast, ep.podcast_id)
        podcast_title = podcast.title if podcast else ""
        episode_title = ep.title
        podcast_id = ep.podcast_id
        published = ep.published.isoformat() if ep.published else ""
        ep_speakers = dict(ep.speakers or {})

    transcript = storage.read_transcript(transcript_file)
    merged_speakers = {**transcript.speakers, **ep_speakers}
    merged_transcript = Transcript(
        episode_id=episode_id,
        model=transcript.model,
        speakers=merged_speakers,
        segments=transcript.segments,
    )

    passages = chunk_transcript(
        merged_transcript,
        podcast_id=podcast_id,
        episode_title=episode_title,
        podcast_title=podcast_title,
        published=published,
    )

    on_progress(0.3, f"Embedding {len(passages)} passages")
    _delete_source(store, episode_id, "transcript")

    if passages:
        embeddings = get_embedder().embed([p.text for p in passages])
        on_progress(0.8, "Writing passages to vector store")
        store.upsert(passages, embeddings)

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.indexed_at = utcnow()
            ep.passage_count = _episode_total_passages(store, episode_id, len(passages))
            session.add(ep)
            session.commit()

    on_progress(1.0, f"Indexed {len(passages)} passages")
    return len(passages)


def index_summary(episode_id: int) -> int:
    """Chunk, embed, and upsert an episode's ``summary.md`` into the vector store."""
    store = get_vector_store()

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is None or not ep.summary_path:
            return 0
        summary_file = storage.to_abs(ep.summary_path)
        if not summary_file.exists():
            return 0
        podcast = session.get(Podcast, ep.podcast_id)
        podcast_title = podcast.title if podcast else ""
        episode_title = ep.title
        podcast_id = ep.podcast_id
        published = ep.published.isoformat() if ep.published else ""

    summary_text = summary_file.read_text(encoding="utf-8")
    passages = _chunk_markdown_summary(
        summary_text,
        episode_id=episode_id,
        podcast_id=podcast_id,
        episode_title=episode_title,
        podcast_title=podcast_title,
        published=published,
    )

    _delete_source(store, episode_id, "summary")
    if passages:
        embeddings = get_embedder().embed([p.text for p in passages])
        store.upsert(passages, embeddings)

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.passage_count = _episode_total_passages(
                store, episode_id, ep.passage_count + len(passages)
            )
            if ep.indexed_at is None and passages:
                ep.indexed_at = utcnow()
            session.add(ep)
            session.commit()

    return len(passages)


def remove_episode(episode_id: int) -> int:
    """Delete all vectors for ``episode_id`` and clear its indexed status."""
    removed = get_vector_store().delete_episode(episode_id)
    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.indexed_at = None
            ep.passage_count = 0
            session.add(ep)
            session.commit()
    return removed


def rebuild_index(on_progress: ProgressFn = _noop_progress) -> int:
    """Re-embed every episode whose transcript (and/or summary) exists on disk."""
    on_progress(0.0, "Scanning episodes on disk")
    store = get_vector_store()

    with db.session_scope() as session:
        episodes = list(session.exec(select(Episode).order_by(Episode.id)).all())

    eligible: list[tuple[int, str, bool, bool]] = []
    valid_ids: set[int] = set()

    for ep in episodes:
        if ep.id is None:
            continue
        has_transcript = bool(ep.transcript_path and storage.to_abs(ep.transcript_path).exists())
        has_summary = bool(ep.summary_path and storage.to_abs(ep.summary_path).exists())
        if has_transcript or has_summary:
            eligible.append((ep.id, ep.title, has_transcript, has_summary))
            valid_ids.add(ep.id)

    for stale_id in store.episode_ids() - valid_ids:
        store.delete_episode(stale_id)

    with db.session_scope() as session:
        for ep in session.exec(select(Episode)).all():
            if ep.id is not None and ep.id not in valid_ids and ep.indexed_at is not None:
                ep.indexed_at = None
                ep.passage_count = 0
                session.add(ep)
        session.commit()

    if not eligible:
        on_progress(1.0, "No transcribed episodes to index")
        return 0

    total_written = 0
    total_eps = len(eligible)
    for idx, (ep_id, title, has_transcript, has_summary) in enumerate(eligible):
        on_progress(idx / total_eps, f"Re-indexing {title}")
        store.delete_episode(ep_id)
        if has_transcript:
            total_written += index_episode(ep_id, force=True)
        if has_summary:
            total_written += index_summary(ep_id)

    on_progress(1.0, f"Rebuilt index ({total_written} passages)")
    return total_written
