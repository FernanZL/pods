"""Transcript health check, run after transcription (and on demand).

Mechanical checks (free, deterministic):
- gaps       stretches of audio with no transcript (a failed or empty chunk)
- loops      the transcription model repeating itself
- speakers   implausible shares (one voice holding nearly everything) and noise labels
- coverage   transcript ending long before the audio does

One cheap model call checks the speaker names (a swapped host/guest would corrupt
every quote and book). A confident swap is corrected; doubts are only reported.
The check never blocks: the episode stays usable and the issues are shown.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from app import db, storage
from app.config import get_settings
from app.domain import ChatMessage, Transcript
from app.models import Episode, Podcast, utcnow
from app.providers import get_llm

log = logging.getLogger(__name__)

GAP_SECONDS = 45.0  # silence-free stretch with no words is suspicious beyond this
LOOP_REPEATS = 3  # the same sentence this many times in a row
NOISE_SHARE = 0.01


def _issue(kind: str, severity: str, message: str, at: float | None = None) -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "message": message, "at": at}


def mechanical_issues(transcript: Transcript, audio_seconds: float | None) -> list[dict[str, Any]]:
    segs = sorted(transcript.segments, key=lambda s: s.start)
    issues: list[dict[str, Any]] = []
    if not segs:
        return [_issue("empty", "high", "The transcript is empty.")]

    # gaps between segments, and at the start/end of the audio
    prev_end = 0.0
    for s in segs:
        if s.start - prev_end >= GAP_SECONDS:
            issues.append(
                _issue(
                    "gap",
                    "high" if s.start - prev_end > 180 else "medium",
                    f"{storage.fmt_ts(s.start - prev_end)} with no transcript "
                    f"({storage.fmt_ts(prev_end)} to {storage.fmt_ts(s.start)}).",
                    prev_end,
                )
            )
        prev_end = max(prev_end, s.end)
    if audio_seconds and audio_seconds - prev_end > max(90.0, audio_seconds * 0.03):
        issues.append(
            _issue(
                "coverage",
                "high",
                f"The transcript ends at {storage.fmt_ts(prev_end)} but the audio runs to "
                f"{storage.fmt_ts(audio_seconds)}.",
                prev_end,
            )
        )

    # loops: one sentence repeated back to back
    sentences: list[tuple[str, float]] = []
    for s in segs:
        for sent in re.split(r"(?<=[.!?])\s+", s.text):
            norm = re.sub(r"\W+", " ", sent.lower()).strip()
            if len(norm.split()) >= 4:
                sentences.append((norm, s.start))
    run, flagged_at = 1, -1.0
    for i in range(1, len(sentences)):
        run = run + 1 if sentences[i][0] == sentences[i - 1][0] else 1
        if run == LOOP_REPEATS and sentences[i][1] != flagged_at:
            flagged_at = sentences[i][1]
            issues.append(
                _issue(
                    "loop",
                    "high",
                    f'Repeated text near {storage.fmt_ts(flagged_at)}: "{sentences[i][0][:60]}..."',
                    flagged_at,
                )
            )

    # speakers
    talk: Counter[str] = Counter()
    count: Counter[str] = Counter()
    for s in segs:
        talk[s.speaker] += max(0.0, s.end - s.start)
        count[s.speaker] += 1
    total = sum(talk.values()) or 1.0
    noise = [k for k in talk if talk[k] / total < NOISE_SHARE and count[k] <= 3]
    if noise:
        names = ", ".join(transcript.speakers.get(k, k) for k in noise)
        issues.append(
            _issue("noise_speaker", "low", f"Stray speaker labels ignored in books: {names}.")
        )
    real = [k for k in talk if k not in noise]
    if len(real) == 1:
        issues.append(
            _issue("one_speaker", "medium", "Only one voice was detected in this episode.")
        )
    elif real:
        top = max(real, key=lambda k: talk[k])
        if talk[top] / total > 0.95:
            issues.append(
                _issue(
                    "speaker_share",
                    "medium",
                    f"{transcript.speakers.get(top, top)} holds {talk[top] / total:.0%} of the "
                    "talk time; voices may have been merged.",
                )
            )
    return issues


def _names_messages(transcript: Transcript, ctx: dict[str, str]) -> list[ChatMessage]:
    talk: Counter[str] = Counter()
    for s in transcript.segments:
        talk[s.speaker] += s.end - s.start
    main = [k for k, _ in talk.most_common(4)]
    sample = "\n".join(
        f"[{s.speaker}] {s.text.strip()[:300]}"
        for s in transcript.segments[:70]
        if s.speaker in main
    )
    mapping = {k: transcript.speakers.get(k, k) for k in main}
    return [
        {
            "role": "system",
            "content": (
                "You check speaker names in a diarized podcast transcript. Given the podcast, "
                "episode metadata, the current label->name mapping and the opening segments, "
                "decide whether each label is named correctly (hosts usually introduce the "
                "show and the guest; guests are often addressed by name). Return ONLY JSON: "
                '{"ok": true|false, "confidence": "high"|"medium"|"low", '
                '"names": {"<label>": "<correct name>"}, "reason": "one sentence"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Podcast: {ctx['podcast']}\nEpisode: {ctx['title']}\n"
                f"Description: {ctx['description'][:1200]}\n"
                f"Current mapping: {json.dumps(mapping)}\n\nOpening segments:\n{sample}"
            ),
        },
    ]


def check_names(transcript: Transcript, ctx: dict[str, str]) -> dict[str, Any]:
    """Ask the model whether speaker names are right. Returns its verdict."""
    raw = get_llm().complete(_names_messages(transcript, ctx), max_tokens=400, json_object=True)
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start : end + 1]) if start >= 0 else {}
    names = {
        str(k): str(v).strip()
        for k, v in (data.get("names") or {}).items()
        if str(k) in transcript.speakers and str(v).strip()
    }
    return {
        "ok": bool(data.get("ok", True)),
        "confidence": str(data.get("confidence") or "low"),
        "names": names,
        "reason": str(data.get("reason") or ""),
    }


def run_check(episode_id: int, *, names: bool = True) -> dict[str, Any]:
    """Check an episode's transcript, apply a confident name correction, store the result."""
    settings = get_settings()
    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is None or not ep.transcript_path:
            raise ValueError("This episode has no transcript to check")
        podcast = session.get(Podcast, ep.podcast_id)
        path = storage.to_abs(ep.transcript_path)
        audio_seconds = float(ep.duration_seconds) if ep.duration_seconds else None
        ctx = {
            "podcast": podcast.title if podcast else "",
            "title": ep.title,
            "description": ep.description or "",
        }
    transcript = storage.read_transcript(path)
    issues = mechanical_issues(transcript, audio_seconds)
    corrected: dict[str, str] = {}
    names_checked = False

    if names and settings.llm_provider != "fake" and len(transcript.speakers) > 1:
        try:
            verdict = check_names(transcript, ctx)
            names_checked = True
            changes = {k: v for k, v in verdict["names"].items() if transcript.speakers.get(k) != v}
            if changes and not verdict["ok"] and verdict["confidence"] == "high":
                before = {k: transcript.speakers.get(k, k) for k in changes}
                transcript.speakers.update(changes)
                storage.write_transcript(path, transcript)
                corrected = changes
                issues.append(
                    _issue(
                        "names_fixed",
                        "medium",
                        "Speaker names corrected: "
                        + "; ".join(f"{before[k]} -> {v}" for k, v in changes.items())
                        + f". {verdict['reason']}",
                    )
                )
            elif changes:
                issues.append(
                    _issue(
                        "names_doubt",
                        "medium",
                        f"Speaker names may be wrong ({verdict['confidence']} confidence): "
                        + "; ".join(
                            f"{transcript.speakers.get(k, k)} -> {v}?" for k, v in changes.items()
                        )
                        + f". {verdict['reason']}",
                    )
                )
        except Exception as exc:  # the check must never break transcription
            log.warning("transcript check: name verification failed: %s", exc)

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order.get(i["severity"], 3), i["at"] or 0))
    result = {
        "ok": not any(i["severity"] in ("high", "medium") for i in issues),
        "issues": issues,
        "names_checked": names_checked,
        "checked_at": utcnow().isoformat(),
    }
    with db.session_scope() as session:
        ep = session.get(Episode, episode_id)
        if ep is not None:
            ep.transcript_check = result
            if corrected:
                ep.speakers = dict(transcript.speakers)
            session.add(ep)
            session.commit()
    return result
