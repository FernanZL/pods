"""End-to-end episode transcription pipeline (chunking, diarization, naming)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from app import db, spend, storage
from app.config import get_settings
from app.domain import (
    ChatMessage,
    KnownSpeaker,
    ProgressFn,
    Segment,
    Transcript,
    TranscriptionContext,
)
from app.models import Episode, Podcast, utcnow
from app.providers import get_llm, get_transcriber
from app.providers.transcription.fake import FakeTranscriber
from app.services import audio
from app.services.downloader import download_episode

log = logging.getLogger(__name__)

MERGE_MAX_GAP_SECONDS = 1.5
_HEARTBEAT_SECONDS = 5.0
SPEAKER_NAMING_SEGMENTS = 40
_UNKNOWN_MARKERS = frozenset({"", "unknown", "none", "null", "n/a", "?"})


def _noop_progress(_fraction: float, _message: str) -> None:
    return None


def _with_offset(seg: Segment, offset: float) -> Segment:
    return Segment(
        speaker=seg.speaker,
        start=round(seg.start + offset, 3),
        end=round(seg.end + offset, 3),
        text=seg.text.strip(),
    )


def merge_segments(
    segments: list[Segment],
    max_gap: float = MERGE_MAX_GAP_SECONDS,
) -> list[Segment]:
    """Merge consecutive segments with the same speaker when gap < max_gap."""
    if not segments:
        return []
    merged: list[Segment] = [
        Segment(
            speaker=segments[0].speaker,
            start=segments[0].start,
            end=segments[0].end,
            text=segments[0].text.strip(),
        )
    ]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg.start - prev.end
        if seg.speaker == prev.speaker and gap < max_gap:
            prev.end = max(prev.end, seg.end)
            piece = seg.text.strip()
            if piece:
                prev.text = f"{prev.text} {piece}".strip()
        else:
            merged.append(
                Segment(
                    speaker=seg.speaker,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                )
            )
    return merged


def _build_known_speakers(
    chunk_path: Path,
    segments: list[Segment],
    workdir: Path,
    max_speakers: int,
) -> list[KnownSpeaker]:
    """Extract 2-10s reference clips from chunk 1 for consistent speaker labels."""
    labels = list(dict.fromkeys(seg.speaker for seg in segments if seg.speaker))
    known: list[KnownSpeaker] = []
    workdir.mkdir(parents=True, exist_ok=True)

    for label in labels[:max_speakers]:
        spk_segs = [seg for seg in segments if seg.speaker == label]
        if not spk_segs:
            continue
        best = max(spk_segs, key=lambda s: s.end - s.start)
        clip_start = max(0.0, best.start)
        raw_dur = max(0.0, best.end - clip_start)
        clip_dur = min(10.0, max(2.0, raw_dur))
        clip_end = clip_start + clip_dur

        safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", label) or "spk"
        ref_path = workdir / f"ref_{safe_label}.mp3"
        audio.cut_clip(chunk_path, clip_start, clip_end, ref_path)
        known.append(KnownSpeaker(name=label, reference_path=ref_path))

    return known


def _default_speaker_name(label: str) -> str:
    if label.lower().startswith("speaker "):
        return label
    if re.fullmatch(r"S\d+", label):
        return f"Speaker {label[1:]}"
    return f"Speaker {label}"


def name_speakers(
    segments: list[Segment],
    context: TranscriptionContext,
) -> dict[str, str]:
    """Infer display names for diarized speaker labels using one LLM JSON call."""
    labels = list(dict.fromkeys(seg.speaker for seg in segments if seg.speaker))
    if not labels:
        return {}

    sample_lines = [f"[{seg.speaker}] {seg.text}" for seg in segments[:SPEAKER_NAMING_SEGMENTS]]
    desc_excerpt = context.description[:1500]
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": (
                "Identify the real names of podcast speakers from metadata and transcript "
                "excerpts. Return a JSON object mapping each speaker label to a full name, "
                'or "unknown" when a speaker cannot be identified confidently.'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Podcast: {context.podcast_title}\n"
                f"Episode: {context.title}\n"
                f"Description: {desc_excerpt}\n"
                f"Speaker labels: {', '.join(labels)}\n\n"
                "Opening transcript segments:\n" + "\n".join(sample_lines)
            ),
        },
    ]

    raw = get_llm().complete(messages, json_object=True)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    speakers: dict[str, str] = {}
    for label in labels:
        candidate = parsed.get(label)
        if isinstance(candidate, str):
            cleaned = candidate.strip()
            if cleaned.lower() not in _UNKNOWN_MARKERS:
                speakers[label] = cleaned
                continue
        speakers[label] = _default_speaker_name(label)
    return speakers


def transcribe_episode(
    episode_id: int,
    on_progress: ProgressFn = _noop_progress,
    force: bool = False,
) -> Transcript:
    """Run the full diarized transcription pipeline for an episode."""
    with db.session_scope() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"Episode {episode_id} not found")
        podcast = session.get(Podcast, episode.podcast_id)
        if podcast is None:
            raise ValueError(f"Podcast {episode.podcast_id} not found")

        if not force and episode.transcribed_at is not None and episode.transcript_path:
            existing = storage.to_abs(episode.transcript_path)
            if existing.is_file():
                on_progress(1.0, "Transcript already exists")
                return storage.read_transcript(existing)

        ep_dir = storage.episode_dir(podcast, episode)
        audio_rel = episode.audio_path
        downloaded_at = episode.downloaded_at
        context = TranscriptionContext(
            episode_id=episode_id,
            title=episode.title,
            description=episode.description,
            podcast_title=podcast.title,
        )

    audio_path: Path | None = None
    if downloaded_at is not None and audio_rel:
        candidate_audio = storage.to_abs(audio_rel)
        if candidate_audio.is_file():
            audio_path = candidate_audio
    if audio_path is None:
        audio_path = download_episode(
            episode_id,
            on_progress=lambda frac, msg: on_progress(frac * 0.1, msg),
            force=False,
        )

    settings = get_settings()
    transcriber = get_transcriber()
    workdir = ep_dir / "work"

    with spend.metering() as tx_meter:
        try:
            if isinstance(transcriber, FakeTranscriber):
                chunks = [audio.AudioChunk(path=audio_path, offset=0.0, duration=0.0)]
            else:
                on_progress(0.1, "Preparing audio chunks")
                chunks = audio.prepare_chunks(
                    audio_path,
                    workdir,
                    settings.audio_chunk_seconds,
                    settings.audio_bitrate_kbps,
                )

            all_segments: list[Segment] = []
            if chunks:
                total = len(chunks)
                started = time.monotonic()
                pool = ThreadPoolExecutor(max_workers=max(1, settings.transcribe_parallelism))

                def _elapsed() -> str:
                    return storage.fmt_ts(time.monotonic() - started)

                def _run(chunk: audio.AudioChunk, known: list[KnownSpeaker]) -> list[Segment]:
                    t0 = time.monotonic()
                    segs = transcriber.transcribe_chunk(
                        chunk.path, known_speakers=known, context=context
                    )
                    log.info(
                        "episode %s: %s transcribed in %.0fs (%d segments)",
                        episode_id,
                        chunk.path.name,
                        time.monotonic() - t0,
                        len(segs),
                    )
                    return segs

                try:
                    # Chunk 1 runs alone: its speakers become the reference voices for the rest.
                    first_chunk = chunks[0]
                    first_future = spend.submit(pool, _run, first_chunk, [])
                    while True:
                        try:
                            first_segs = first_future.result(timeout=_HEARTBEAT_SECONDS)
                            break
                        except FuturesTimeout:
                            on_progress(
                                0.15,
                                f"Chunk 1/{total}: identifying speakers · {_elapsed()} elapsed",
                            )
                    if transcriber.supports_diarization:
                        # Stable labels that can't collide with the API's per-request "A"/"B"
                        # labels for voices first heard in a later chunk.
                        first_labels = dict.fromkeys(s.speaker for s in first_segs)
                        stable = {label: f"S{i}" for i, label in enumerate(first_labels, 1)}
                        for seg in first_segs:
                            seg.speaker = stable.get(seg.speaker, seg.speaker)
                    all_segments.extend(_with_offset(seg, first_chunk.offset) for seg in first_segs)

                    known_speakers: list[KnownSpeaker] = []
                    if total > 1 and transcriber.supports_diarization:
                        on_progress(0.25, "Extracting speaker reference clips")
                        known_speakers = _build_known_speakers(
                            first_chunk.path,
                            first_segs,
                            workdir,
                            settings.max_known_speakers,
                        )

                    # Remaining chunks run in parallel; results are reassembled in order.
                    pending = {spend.submit(pool, _run, c, known_speakers): c for c in chunks[1:]}
                    done_count = 1
                    while pending:
                        finished, _ = wait(
                            pending, timeout=_HEARTBEAT_SECONDS, return_when=FIRST_COMPLETED
                        )
                        for fut in finished:
                            chunk = pending.pop(fut)
                            all_segments.extend(_with_offset(s, chunk.offset) for s in fut.result())
                            done_count += 1
                        on_progress(
                            0.25 + 0.60 * (done_count / total),
                            f"Transcribed {done_count}/{total} chunks · {_elapsed()} elapsed",
                        )
                finally:
                    # On cancel or error, drop chunks that have not started yet.
                    pool.shutdown(wait=False, cancel_futures=True)

                all_segments.sort(key=lambda s: s.start)

            merged = merge_segments(all_segments)
            on_progress(0.9, "Naming speakers")
            speakers = name_speakers(merged, context)

            transcript = Transcript(
                episode_id=episode_id,
                model=transcriber.name,
                speakers=speakers,
                segments=merged,
            )
            transcript_path = ep_dir / "transcript.json"
            storage.write_transcript(transcript_path, transcript)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.transcript_path = storage.to_rel(transcript_path)
            ep.transcribed_at = utcnow()
            ep.speakers = speakers
            if tx_meter.by_model:
                minutes = (merged[-1].end if merged else 0.0) / 60.0
                ep.transcribe_cost = tx_meter.to_dict() | {"minutes": round(minutes, 2)}
            session.add(ep)
            session.commit()

    on_progress(0.97, "Checking the transcript")
    try:
        from app.services.transcript_check import run_check

        run_check(episode_id)
    except Exception as exc:  # a failed check never fails the transcription
        log.warning("episode %s: transcript check failed: %s", episode_id, exc)
    on_progress(1.0, "Transcription complete")
    return transcript
