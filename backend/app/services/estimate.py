"""Cost estimation for selected episodes and pipeline steps."""

from __future__ import annotations

from sqlmodel import Session, col, select

from app import db
from app.config import get_settings
from app.jobs.worker import episode_needs_step, resolve_selection
from app.models import Episode
from app.schemas import CostEstimate, SelectionRequest, Step

WORDS_PER_MINUTE = 160.0
TOKENS_PER_WORD = 1.35
SPEAKER_NAMING_INPUT_TOKENS = 3_000.0
SPEAKER_NAMING_OUTPUT_TOKENS = 300.0
_CANONICAL_STEPS: tuple[Step, ...] = ("download", "transcribe", "index")


MIN_MEASURED_MINUTES = 5.0


def transcription_rate(session: Session) -> tuple[float, bool]:
    """USD per audio minute for the configured transcriber, and whether it was measured.

    Uses the metered cost of past transcriptions with the same model when there are
    at least a few minutes of them; otherwise the configured per-minute price.
    """
    s = get_settings()
    diarize = s.transcriber == "openai_diarize"
    model = s.diarize_model if diarize else s.text_transcribe_model
    default = s.price_diarize_per_min if diarize else s.price_text_transcribe_per_min
    usd = minutes = 0.0
    rows = session.exec(select(Episode).where(col(Episode.transcribed_at).is_not(None))).all()
    for ep in rows:
        cost = ep.transcribe_cost if isinstance(ep.transcribe_cost, dict) else {}
        spent = (cost.get("by_model") or {}).get(model)
        mins = float(cost.get("minutes") or 0.0)
        if spent and mins > 0:
            usd += float(spent.get("usd") or 0.0)
            minutes += mins
    if minutes >= MIN_MEASURED_MINUTES and usd > 0:
        return usd / minutes, True
    return default, False


def estimate(sel: SelectionRequest) -> CostEstimate:
    """Estimate transcription, embedding, and LLM speaker-naming USD costs."""
    settings = get_settings()
    ordered_steps: list[Step] = [s for s in _CANONICAL_STEPS if s in sel.steps]

    speaker_llm_cost = (
        SPEAKER_NAMING_INPUT_TOKENS / 1_000_000.0
    ) * settings.price_llm_input_per_mtok + (
        SPEAKER_NAMING_OUTPUT_TOKENS / 1_000_000.0
    ) * settings.price_llm_output_per_mtok

    with db.session_scope() as session:
        transcribe_per_min, measured = transcription_rate(session)
        episodes = resolve_selection(session, sel)

        episode_count = 0
        known_minutes = 0.0
        unknown_duration_count = 0
        skipped_already_done = 0
        transcription_usd = 0.0
        embedding_usd = 0.0
        llm_usd = 0.0

        for ep in episodes:
            todo = [step for step in ordered_steps if episode_needs_step(ep, step, force=sel.force)]
            if not todo:
                skipped_already_done += 1
                continue

            episode_count += 1
            if ep.duration_seconds is not None and ep.duration_seconds > 0:
                minutes = ep.duration_seconds / 60.0
                known_minutes += minutes
            else:
                minutes = 0.0
                unknown_duration_count += 1

            if "transcribe" in todo:
                transcription_usd += minutes * transcribe_per_min
                llm_usd += speaker_llm_cost

            if "index" in todo:
                embed_tokens = minutes * WORDS_PER_MINUTE * TOKENS_PER_WORD
                embedding_usd += (embed_tokens / 1_000_000.0) * settings.price_embedding_per_mtok

    transcription_usd = round(transcription_usd, 6)
    embedding_usd = round(embedding_usd, 6)
    llm_usd = round(llm_usd, 6)
    total_usd = round(transcription_usd + embedding_usd + llm_usd, 6)

    return CostEstimate(
        episode_count=episode_count,
        known_minutes=round(known_minutes, 2),
        unknown_duration_count=unknown_duration_count,
        transcription_usd=transcription_usd,
        embedding_usd=embedding_usd,
        llm_usd=llm_usd,
        total_usd=total_usd,
        skipped_already_done=skipped_already_done,
        transcription_per_min=round(transcribe_per_min, 5),
        rate_measured=measured,
    )
