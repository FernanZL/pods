"""Quote verification: a quote is only real if its exact words exist in the transcript.

Attribution comes from the segment that contains the words, never from the
writer's claim, so a misattributed or invented quote cannot reach the PDF.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.books.document import Quote
from app.domain import Transcript

_QUOTE_CHARS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    text = text.translate(_QUOTE_CHARS).lower()
    text = re.sub(r"[^\w\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class QuoteNotFound(ValueError):
    pass


def find_quote(transcript: Transcript, text: str) -> Quote:
    """Return the verified Quote for `text`, attributed to the segment that contains it.

    Matching ignores case, punctuation and whitespace. A quote may run across two
    consecutive segments by the same speaker.
    """
    needle = normalize(text)
    if len(needle.split()) < 3:
        raise QuoteNotFound(f"quote too short to verify: {text!r}")
    segs = transcript.segments
    for i, seg in enumerate(segs):
        window = normalize(seg.text)
        if needle in window:
            return _quote(transcript, seg.speaker, seg.start, text)
        if i + 1 < len(segs) and segs[i + 1].speaker == seg.speaker:
            joined = f"{window} {normalize(segs[i + 1].text)}"
            if needle in joined:
                return _quote(transcript, seg.speaker, seg.start, text)
    raise QuoteNotFound(f"not found verbatim in the transcript: {text!r}")


def _quote(transcript: Transcript, label: str, start: float, text: str) -> Quote:
    name = transcript.speakers.get(label, f"Speaker {label}")
    return Quote(text=text.strip().strip('"“”'), speaker=name, start=start)


def verify_all(transcript: Transcript, texts: Sequence[str]) -> tuple[list[Quote], list[str]]:
    """Verify many quotes; returns (verified, rejected texts)."""
    ok: list[Quote] = []
    bad: list[str] = []
    for t in texts:
        try:
            ok.append(find_quote(transcript, t))
        except QuoteNotFound:
            bad.append(t)
    return ok, bad


_MARKED = re.compile(r"⟦(.+?)⟧", re.S)


def resolve_runs(transcript: Transcript, text: str) -> tuple[list[str | Quote], list[str]]:
    """Split writer text into runs, turning each ⟦marked quote⟧ into a verified Quote.

    A marked passage that cannot be verified loses its quotation status and stays as
    plain narrative text, so it is never presented as something a speaker said.
    Returns (runs, rejected).
    """
    runs: list[str | Quote] = []
    rejected: list[str] = []
    pos = 0
    for m in _MARKED.finditer(text):
        if m.start() > pos:
            runs.append(text[pos : m.start()])
        try:
            runs.append(find_quote(transcript, m.group(1)))
        except QuoteNotFound:
            rejected.append(m.group(1))
            runs.append(m.group(1))
        pos = m.end()
    if pos < len(text):
        runs.append(text[pos:])
    # merge adjacent plain strings
    merged: list[str | Quote] = []
    for r in runs:
        if isinstance(r, str) and merged and isinstance(merged[-1], str):
            merged[-1] = merged[-1] + r
        else:
            merged.append(r)
    return merged, rejected
