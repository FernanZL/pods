"""Quote verification: a quote is only real if its words exist in the transcript.

The transcript is treated as one continuous stream of words, so a quote that
crosses a segment boundary (diarization often splits mid-phrase) still matches.
Attribution comes from the transcript, never from the writer: the speaker who
says most of the matched words, at the start time of the first segment touched.

Matching is case- and punctuation-insensitive. A near-verbatim quote (small
slips such as a dropped word) is snapped to the speaker's exact words when the
token similarity is high enough; anything else is rejected.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.books.document import Quote
from app.domain import Transcript

_QUOTE_CHARS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
FUZZY_MIN = 0.86  # token similarity needed to snap a near-verbatim quote
HIDDEN_MIN_WORDS = 8  # unquoted runs of this many transcript words may become quotes
HIDDEN_PLAIN_WORDS = 10  # ...without first-person words they must be at least this long
_FIRST_PERSON = {"i", "i'm", "i've", "i'd", "i'll", "me", "my", "mine", "we", "we're", "our", "us"}
_EDGE_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "of",
    "to",
    "in",
    "on",
    "at",
    "for",
    "with",
    "that",
    "as",
    "by",
    "from",
    "how",
}


def normalize(text: str) -> str:
    text = text.translate(_QUOTE_CHARS).lower()
    text = re.sub(r"[^\w\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_token(word: str) -> str:
    return normalize(word).replace(" ", "")


class QuoteNotFound(ValueError):
    pass


@dataclass
class _Index:
    """The transcript as one token stream, with the segment each token came from."""

    words: list[str]  # original words (with punctuation)
    norm: list[str]  # normalised tokens
    seg_of: list[int]  # segment index per token
    first_tok: dict[str, list[int]]  # token -> positions


_cache: dict[int, _Index] = {}


def _index(transcript: Transcript) -> _Index:
    key = id(transcript)
    if key in _cache:
        return _cache[key]
    words, norm, seg_of = [], [], []
    for i, seg in enumerate(transcript.segments):
        for w in seg.text.split():
            n = _norm_token(w)
            if not n:
                continue
            words.append(w)
            norm.append(n)
            seg_of.append(i)
    first: dict[str, list[int]] = defaultdict(list)
    for pos, tok in enumerate(norm):
        first[tok].append(pos)
    idx = _Index(words, norm, seg_of, dict(first))
    if len(_cache) > 16:
        _cache.clear()
    _cache[key] = idx
    return idx


def _tokens(text: str) -> list[str]:
    return [t for t in (_norm_token(w) for w in text.split()) if t]


def _make_quote(transcript: Transcript, idx: _Index, lo: int, hi: int, text: str) -> Quote:
    """Quote for token span [lo, hi): majority speaker, start of first segment."""
    counts: dict[str, int] = defaultdict(int)
    for p in range(lo, hi):
        counts[transcript.segments[idx.seg_of[p]].speaker] += 1
    label = max(counts, key=counts.get)
    start = transcript.segments[idx.seg_of[lo]].start
    name = transcript.speakers.get(label, f"Speaker {label}")
    return Quote(text=text.strip().strip('"“”'), speaker=name, start=start)


def _exact(idx: _Index, needle: list[str]) -> int | None:
    n = len(needle)
    for pos in idx.first_tok.get(needle[0], []):
        if idx.norm[pos : pos + n] == needle:
            return pos
    return None


def _fuzzy(idx: _Index, needle: list[str]) -> tuple[int, int] | None:
    """Best near-verbatim window, located via shared 3-grams."""
    n = len(needle)
    if n < 5:
        return None
    anchors: set[int] = set()
    for k in range(n - 2):
        gram = needle[k : k + 3]
        for pos in idx.first_tok.get(gram[0], []):
            if idx.norm[pos : pos + 3] == gram:
                anchors.add(max(0, pos - k))
    best, best_span = 0.0, None
    for a in anchors:
        for length in range(max(3, n - 3), n + 4):
            window = idx.norm[a : a + length]
            sm = SequenceMatcher(None, needle, window, autojunk=False)
            ratio = sm.ratio()
            if ratio > best:
                # trim to the stretch that actually aligns (runs of 2+ tokens), so stray
                # transcript words at the edges are not pulled into the quote
                matched = [b for b in sm.get_matching_blocks() if b.size]
                big = [b for b in matched if b.size >= 2]
                if not big:
                    continue
                start, end = big[0].b, big[-1].b + big[-1].size
                for blk in matched:  # a lone last word just after a slip ("my"/"your hand")
                    if blk.b >= end and blk.b - end <= 2:
                        end = blk.b + blk.size
                best = ratio
                best_span = (a + start, a + end)
    return best_span if best >= FUZZY_MIN else None


def find_quote(transcript: Transcript, text: str) -> Quote:
    """Return the verified Quote for `text`.

    Exact matches keep the writer's wording (it is the transcript's, modulo
    punctuation); near-verbatim matches are replaced by the transcript's own words.
    """
    needle = _tokens(text)
    if len(needle) < 3:
        raise QuoteNotFound(f"quote too short to verify: {text!r}")
    idx = _index(transcript)
    pos = _exact(idx, needle)
    if pos is not None:
        return _make_quote(transcript, idx, pos, pos + len(needle), text)
    span = _fuzzy(idx, needle)
    if span is not None:
        lo, hi = span
        exact_words = " ".join(idx.words[lo:hi]).strip(" ,;:")
        return _make_quote(transcript, idx, lo, hi, exact_words)
    raise QuoteNotFound(f"not found in the transcript: {text!r}")


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


def _merge(runs: list[str | Quote]) -> list[str | Quote]:
    merged: list[str | Quote] = []
    for r in runs:
        if isinstance(r, str) and merged and isinstance(merged[-1], str):
            merged[-1] = merged[-1] + r
        elif not (isinstance(r, str) and r == ""):
            merged.append(r)
    return merged


def resolve_runs(transcript: Transcript, text: str) -> tuple[list[str | Quote], list[str]]:
    """Split writer text into runs, turning each ⟦marked quote⟧ into a verified Quote.

    A marked passage that cannot be verified stays as plain text; `recover_hidden`
    then re-quotes any stretch of it that is still the speaker's own words.
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
    return recover_hidden(transcript, _merge(runs)), rejected


def recover_hidden(transcript: Transcript, runs: list[str | Quote]) -> list[str | Quote]:
    """Turn unquoted stretches of >= HIDDEN_MIN_WORDS transcript words into cited quotes,
    so a speaker's words never read as the narrator's."""
    idx = _index(transcript)
    out: list[str | Quote] = []
    for run in runs:
        if not isinstance(run, str):
            out.append(run)
            continue
        out.extend(_split_hidden(transcript, idx, run))
    return _merge(out)


def _split_hidden(transcript: Transcript, idx: _Index, text: str) -> list[str | Quote]:
    spans = [(m.start(), m.end(), _norm_token(m.group())) for m in re.finditer(r"\S+", text)]
    spans = [s for s in spans if s[2]]
    toks = [s[2] for s in spans]
    pieces: list[str | Quote] = []
    cursor_char = 0
    i = 0
    while i < len(toks):
        best_len, best_pos = 0, -1
        for pos in idx.first_tok.get(toks[i], []):
            k = 0
            while (
                i + k < len(toks) and pos + k < len(idx.norm) and idx.norm[pos + k] == toks[i + k]
            ):
                k += 1
            if k > best_len:
                best_len, best_pos = k, pos
        if best_len >= HIDDEN_MIN_WORDS:
            # first person just past the match counts too ("...each movement of my hand")
            window = set(toks[i : i + best_len + 3])
            # A short shared phrase is the narrator echoing the speaker, not hidden speech.
            if best_len < HIDDEN_PLAIN_WORDS and not (window & _FIRST_PERSON):
                i += best_len
                continue
        if best_len >= HIDDEN_MIN_WORDS:
            c0, c1 = spans[i][0], spans[i + best_len - 1][1]
            # Widen to the whole clause the speech sits in ("an admission: I don't know...")
            # and snap that to the transcript, so the quote does not open mid-phrase.
            # A short lead-in ("as having to") is kept as narrative if it does not match.
            clause_start = max(
                cursor_char, max((text.rfind(ch, 0, c0) for ch in ":;.!?\u2014"), default=-1) + 1
            )
            sentence_end = min(
                [p for p in (text.find(ch, c1) for ch in ".;!?") if p >= 0] or [len(text)]
            )
            for lo, hi in ((clause_start, sentence_end), (clause_start, c1), (c0, sentence_end)):
                if lo >= c0 and hi <= c1:
                    continue
                try:
                    q = find_quote(transcript, text[lo:hi])
                except QuoteNotFound:
                    continue
                lead = text[cursor_char:lo]
                pieces.append(lead + (" " if lead and not lead.endswith(" ") else ""))
                pieces.append(q)
                cursor_char = hi
                i = next((k for k, sp in enumerate(spans) if sp[0] >= hi), len(toks))
                break
            else:
                # trim dangling small words at the edges ("...human nature in the")
                lo_t, hi_t = i, i + best_len
                while lo_t < hi_t and toks[lo_t] in _EDGE_WORDS:
                    lo_t += 1
                while hi_t > lo_t and toks[hi_t - 1] in _EDGE_WORDS:
                    hi_t -= 1
                if hi_t - lo_t < HIDDEN_MIN_WORDS - 2:
                    i += best_len
                    continue
                best_pos += lo_t - i
                best_len = hi_t - lo_t
                i = lo_t
                c0, c1 = spans[i][0], spans[i + best_len - 1][1]
                raw = text[c0:c1]
                core = raw.strip(" ,;:.")
                lead = raw[: len(raw) - len(raw.lstrip(" ,;:."))]
                pieces.append(text[cursor_char:c0] + lead)
                pieces.append(_make_quote(transcript, idx, best_pos, best_pos + best_len, core))
                cursor_char = c0 + len(lead) + len(core)
                i += best_len
            continue
        i += 1
    pieces.append(text[cursor_char:])
    return pieces
