"""Episode -> long-form book: plan, write sections in parallel, verify quotes, render.

Flow
  1. size     chapters and target length from the episode's length (a long book,
              not a summary: roughly 70% of the spoken word count, minus filler)
  2. plan     one LLM call reads the whole numbered transcript and returns titles,
              chapters, sections mapped to segment ranges, a glossary, quote picks
  3. write    every section is written in parallel from its own transcript slice,
              with the plan, glossary and neighbouring headings as context
  4. verify   every quote is matched word for word to the transcript; misses are
              demoted to narrative (paragraph quotes) or dropped (pull quotes)
  5. render   seeded theme -> PDF, cover thumbnail, page count

In fake mode (LLM_PROVIDER=fake) steps 2-3 use a deterministic stand-in so the
pipeline runs offline and free.
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app import db, storage
from app.books.document import (
    Block,
    Book,
    Callout,
    Chapter,
    Heading,
    Paragraph,
    PullQuote,
    Quote,
    QuotePair,
    book_from_dict,
    book_to_dict,
    word_count,
)
from app.books.render import render_pdf
from app.books.theme import make_theme
from app.books.verify import QuoteNotFound, find_quote, recover_hidden, resolve_runs
from app.config import get_settings
from app.domain import ChatMessage, ProgressFn, Transcript
from app.models import Book as BookRow
from app.models import Episode, Podcast, utcnow
from app.providers import get_llm

log = logging.getLogger(__name__)

LABELS = [
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen",
]  # fmt: skip

BANNED = [
    "delve", "dive into", "deep dive", "in today's fast-paced world", "it's worth noting",
    "a testament to", "tapestry", "navigate the complexities", "game-changer", "unlock",
    "embark on a journey", "in conclusion", "at the end of the day", "it is important to note",
    "plays a crucial role", "the realm of", "seamlessly", "elevate", "rich tapestry",
    "nestled", "a symphony of", "in a world where",
]  # fmt: skip

STYLE = """Editorial preset: MAGAZINE FEATURE (long-form).
- Voice: a sharp, warm feature writer narrating in the third person about the conversation.
  The narrator is NOT the speakers: never write in a speaker's first person, never invent
  what they think, never put words in their mouths.
- Story-driven: open sections with a concrete moment, question or tension from the talk;
  follow the argument as it develops; keep the examples, stories, numbers, caveats and
  disagreements that make it real. Explain technical ideas plainly without dumbing down.
- Long, not padded: cover everything substantive in the slice in the order it matters.
  Cut repetition, ad reads, sponsor segments, housekeeping and filler. Do not summarise
  the section at its end and do not moralise.
- Rhythm: vary sentence length; short paragraphs (2-5 sentences); concrete verbs; no lists
  inside paragraphs.
- British or American spelling consistently (follow the transcript)."""

QUOTING = """Quoting rules (strict, checked by code against the transcript):
- Wrap every verbatim quote in ⟦ and ⟧ inside paragraph text, e.g. as she puts it, ⟦the
  morning sets the clock⟧. Copy the words EXACTLY from the transcript slice (5-30 words, one
  contiguous passage, no ellipses, no edits). Attribution comes from the transcript, so
  say who is speaking in your own words around the quote.
- Use 2-5 inline quotes per section, plus at most one "pull" quote (a striking line, 8-30
  words, also verbatim). Quotes that do not match the transcript exactly are removed."""


@dataclass
class SectionPlan:
    heading: str
    brief: str
    first: int  # segment indices (inclusive)
    last: int
    target_words: int = 0


@dataclass
class ChapterPlan:
    title: str
    dek: str
    opener: str
    sections: list[SectionPlan] = field(default_factory=list)


@dataclass
class Plan:
    title: str
    title_accent: str
    deck: str
    closing: str
    glossary: list[dict[str, str]]
    chapters: list[ChapterPlan]


# ---------------------------------------------------------------------------- sizing


def sizing(transcript: Transcript) -> tuple[int, int, int]:
    """(transcript words, chapters, target words) for an episode."""
    words = sum(len(s.text.split()) for s in transcript.segments)
    minutes = (transcript.segments[-1].end if transcript.segments else 0) / 60
    chapters = max(3, min(12, round(minutes / 14)))
    # long-form: ~70% of the spoken words, at least 2,500 (never more than was said), max 24k
    target = min(24000, max(int(words * 0.7), min(2500, words)))
    return words, chapters, target


def estimate_cost(transcript: Transcript) -> tuple[int, int, int, float]:
    """(words, chapters, target words, USD) using the configured LLM prices."""
    s = get_settings()
    words, chapters, target = sizing(transcript)
    tok_in = words * 1.35 * 2 + 3000 + 1800 * chapters * 3  # plan + section slices + prompts
    tok_out = 4000 + target * 1.45
    usd = tok_in / 1e6 * s.price_llm_input_per_mtok + tok_out / 1e6 * s.price_llm_output_per_mtok
    return words, chapters, target, round(usd, 4)


# ---------------------------------------------------------------------------- helpers


def _ts(sec: float) -> str:
    return storage.fmt_ts(sec)


def _numbered(transcript: Transcript, first: int = 0, last: int | None = None) -> str:
    segs = transcript.segments
    last = len(segs) - 1 if last is None else last
    lines = []
    for i in range(first, last + 1):
        s = segs[i]
        name = transcript.speakers.get(s.speaker, f"Speaker {s.speaker}")
        lines.append(f"[{i}] {_ts(s.start)} {name}: {s.text.strip()}")
    return "\n".join(lines)


def _json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start : end + 1]) if start >= 0 else {}


def _ask_json(messages: list[ChatMessage], max_tokens: int) -> dict[str, Any]:
    llm = get_llm()
    for attempt in range(2):
        raw = llm.complete(messages, max_tokens=max_tokens, json_object=True)
        try:
            data = _json(raw)
            if data:
                return data
        except (ValueError, json.JSONDecodeError):
            log.warning("book: invalid JSON from model (attempt %d)", attempt + 1)
    raise ValueError("The model did not return valid JSON for the book plan/section")


def _seg_words(transcript: Transcript, first: int, last: int) -> int:
    return sum(len(s.text.split()) for s in transcript.segments[first : last + 1])


# ---------------------------------------------------------------------------- planning


def _plan_messages(transcript: Transcript, ctx: dict[str, str], chapters: int, target: int):
    n = len(transcript.segments)
    system = f"""You are the editor planning a long-form magazine-style book from one podcast
episode. The book retells the conversation as narrative non-fiction: it is long and complete,
NOT a summary.

Return ONLY a JSON object:
{{
  "title": "short, evocative book title (2-6 words, no colon)",
  "title_accent": "the last 1-2 words of the title, to be set in italic",
  "deck": "one or two sentences selling the book",
  "closing_quote": "a memorable verbatim line from the transcript for the last page",
  "glossary": [{{"term": "...", "definition": "one line"}}],
  "chapters": [
    {{
      "title": "chapter title (2-6 words)",
      "dek": "one-sentence standfirst",
      "opener_quote": "a verbatim line from this chapter's range (8-30 words)",
      "sections": [
        {{"heading": "section heading (2-6 words)", "brief": "what this section covers and
          the angle to take, 1-3 sentences", "first": 0, "last": 0}}
      ]
    }}
  ]
}}

Rules:
- About {chapters} chapters, 3-6 sections each, in transcript order.
- "first"/"last" are segment indices [0..{n - 1}]; sections are contiguous, cover the whole
  conversation, and never overlap. Put ads, sponsor reads and housekeeping inside the nearest
  section (the writer will skip them) rather than making a section of them.
- Chapters follow the conversation's real arcs, not equal time slices.
- Quotes must be copied exactly from the transcript.
- Opener and closing quotes must be substantive lines from the conversation itself: never
  the intro, the outro, thanks, sponsor reads, or requests to subscribe/follow/review.
- The whole book will be about {target} words.
{STYLE}"""
    user = (
        f"Podcast: {ctx['podcast']}\nEpisode {ctx['number']}: {ctx['title']}\n"
        f"Description: {ctx['description'][:1500]}\n\nTRANSCRIPT (numbered segments):\n"
        + _numbered(transcript)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_plan(data: dict[str, Any], transcript: Transcript, ctx: dict[str, str]) -> Plan:
    n = len(transcript.segments)
    chapters: list[ChapterPlan] = []
    cursor = 0
    for ch in data.get("chapters") or []:
        cp = ChapterPlan(
            title=str(ch.get("title") or "").strip() or "Untitled",
            dek=str(ch.get("dek") or "").strip(),
            opener=str(ch.get("opener_quote") or "").strip(),
        )
        for sec in ch.get("sections") or []:
            try:
                first, last = int(sec.get("first", cursor)), int(sec.get("last", cursor))
            except (TypeError, ValueError):
                continue
            first = max(cursor, min(first, n - 1))
            last = max(first, min(last, n - 1))
            if first > n - 1 or (first < cursor and last < cursor):
                continue
            cp.sections.append(
                SectionPlan(
                    heading=str(sec.get("heading") or "").strip(),
                    brief=str(sec.get("brief") or "").strip(),
                    first=first,
                    last=last,
                )
            )
            cursor = last + 1
        if cp.sections:
            chapters.append(cp)
    if not chapters:
        raise ValueError("The book plan had no usable chapters")
    # make sure the tail of the conversation is covered
    tail = chapters[-1].sections[-1]
    tail.last = n - 1
    return Plan(
        title=str(data.get("title") or ctx["title"]).strip(),
        title_accent=str(data.get("title_accent") or "").strip(),
        deck=str(data.get("deck") or "").strip(),
        closing=str(data.get("closing_quote") or "").strip(),
        glossary=[g for g in (data.get("glossary") or []) if isinstance(g, dict)][:30],
        chapters=chapters,
    )


def _assign_targets(plan: Plan, transcript: Transcript, target: int) -> None:
    total = max(1, _seg_words(transcript, 0, len(transcript.segments) - 1))
    for ch in plan.chapters:
        for sec in ch.sections:
            share = _seg_words(transcript, sec.first, sec.last) / total
            sec.target_words = max(250, round(target * share / 10) * 10)


# ---------------------------------------------------------------------------- writing


def _section_messages(
    plan: Plan, ci: int, si: int, transcript: Transcript, ctx: dict[str, str]
) -> list[ChatMessage]:
    ch = plan.chapters[ci]
    sec = ch.sections[si]
    outline = "\n".join(
        f"{'>>' if (i, j) == (ci, si) else '  '} Ch{i + 1} {c.title} / {s.heading}"
        for i, c in enumerate(plan.chapters)
        for j, s in enumerate(c.sections)
    )
    gloss = "\n".join(f"- {g.get('term')}: {g.get('definition')}" for g in plan.glossary)
    banned = ", ".join(f'"{b}"' for b in BANNED)
    system = f"""You are writing one section of a long-form book that retells a podcast
conversation as narrative non-fiction.

{STYLE}

{QUOTING}

Never use these words or phrases: {banned}.

Return ONLY a JSON object:
{{"blocks": [
  {{"type": "p", "text": "paragraph with ⟦verbatim quotes⟧"}},
  {{"type": "pull", "quote": "verbatim striking line"}},
  {{"type": "pair", "left": "verbatim line", "right": "verbatim reply"}},
  {{"type": "callout", "title": "From the episode: ...", "items": ["practical step", "..."]}}
]}}
- Mostly "p" blocks. "pull" at most once, roughly mid-section. "pair" only for a real
  back-and-forth exchange (both lines verbatim). "callout" only when the slice gives concrete,
  practical steps (3-5 short items, paraphrased, no invented advice); at most one per section.
- Length: about {sec.target_words} words of paragraph text. Do not stop short; do not pad.
- No headings (the section heading is set by the layout). Do not repeat earlier sections.
- Never narrate the show's own housekeeping: sponsors and ads, links, "subscribe", "follow",
  "leave a review", thanks for listening, intros and outros. If the slice ends with the
  outro, end the section on the last substantive idea instead."""
    user = (
        f"Book: {plan.title}\nPodcast: {ctx['podcast']}, episode {ctx['number']}: "
        f"{ctx['title']}\nChapter {ci + 1}: {ch.title} ({ch.dek})\n"
        f"This section: {sec.heading}\nBrief: {sec.brief}\n\nOutline (>> = this section):\n"
        f"{outline}\n\nGlossary:\n{gloss or '-'}\n\nTRANSCRIPT SLICE:\n"
        + _numbered(transcript, sec.first, sec.last)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass
class Written:
    blocks: list[Block]
    quotes: int
    rejected: int


def _to_blocks(data: dict[str, Any], transcript: Transcript) -> Written:
    blocks: list[Block] = []
    quotes = rejected = 0
    pulls = callouts = 0
    for raw in data.get("blocks") or []:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type")
        try:
            if kind == "p" and str(raw.get("text") or "").strip():
                runs, bad = resolve_runs(transcript, str(raw["text"]).strip())
                rejected += len(bad)
                quotes += sum(1 for r in runs if isinstance(r, Quote))
                blocks.append(Paragraph(runs))
            elif kind == "pull" and pulls == 0:
                blocks.append(PullQuote(find_quote(transcript, str(raw.get("quote") or ""))))
                pulls += 1
                quotes += 1
            elif kind == "pair":
                left = find_quote(transcript, str(raw.get("left") or ""))
                right = find_quote(transcript, str(raw.get("right") or ""))
                blocks.append(QuotePair(left, right))
                quotes += 2
            elif kind == "callout" and callouts == 0:
                items = [str(i).strip() for i in raw.get("items") or [] if str(i).strip()]
                if 2 <= len(items) <= 6:
                    blocks.append(Callout(str(raw.get("title") or "From the episode"), items))
                    callouts += 1
        except QuoteNotFound:
            rejected += 1  # a pull / pair that is not verbatim is dropped entirely
    return Written(blocks, quotes, rejected)


def _write_section(plan: Plan, ci: int, si: int, transcript: Transcript, ctx) -> Written:
    sec = plan.chapters[ci].sections[si]
    data = _ask_json(
        _section_messages(plan, ci, si, transcript, ctx),
        max_tokens=int(sec.target_words * 2.2) + 1500,
    )
    return _to_blocks(data, transcript)


# ----------------------------------------------------------------- fake (offline) mode


def _fake_plan(transcript: Transcript, ctx: dict[str, str], chapters: int) -> Plan:
    segs = transcript.segments
    n = len(segs)
    per = max(1, n // chapters)
    plan_chapters = []
    for c in range(min(chapters, n)):
        lo = c * per
        hi = n - 1 if c == chapters - 1 else min(n - 1, lo + per - 1)
        mid = (lo + hi) // 2
        sections = [
            SectionPlan(f"Movement {k + 1}", "", a, b)
            for k, (a, b) in enumerate([(lo, mid), (mid + 1, hi)] if hi > lo else [(lo, hi)])
        ]
        words = segs[lo].text.split()
        plan_chapters.append(
            ChapterPlan(
                title=" ".join(words[:4]).strip(".,?") or f"Part {c + 1}",
                dek=f"From {_ts(segs[lo].start)} to {_ts(segs[hi].end)} of the conversation.",
                opener=" ".join(words[:12]),
                sections=sections,
            )
        )
    return Plan(
        title=ctx["title"],
        title_accent="",
        deck=ctx["description"][:200],
        closing=" ".join(segs[-1].text.split()[:12]),
        glossary=[],
        chapters=plan_chapters,
    )


def _fake_section(plan: Plan, ci: int, si: int, transcript: Transcript) -> Written:
    sec = plan.chapters[ci].sections[si]
    blocks: list[Block] = []
    for i in range(sec.first, sec.last + 1):
        s = transcript.segments[i]
        name = transcript.speakers.get(s.speaker, s.speaker)
        words = s.text.split()
        if len(words) < 6:
            continue
        text = f"At {_ts(s.start)}, {name} picks up the thread: ⟦{' '.join(words[:10])}⟧."
        runs, _ = resolve_runs(transcript, text)
        blocks.append(Paragraph(runs))
    return Written(blocks, quotes=len(blocks), rejected=0)


# ------------------------------------------------------------------------ assembly


_HOUSEKEEPING = re.compile(
    r"thank(s| you) (so much )?for (joining|listening|watching|tuning)|subscribe|sponsor|"
    r"brought to you|please (follow|rate|review)|leave (us )?a review|patreon|show ?notes|"
    r"welcome to the|link in the|promo code|discount|today'?s episode",
    re.I,
)


def _is_housekeeping(q: Quote, duration: float) -> bool:
    """Intro/outro and podcast admin make poor openers and closers."""
    edge = q.start < duration * 0.02 or q.start > duration * 0.97
    return bool(_HOUSEKEEPING.search(q.text)) or (edge and len(q.text.split()) < 14)


def _verified(transcript: Transcript, text: str, *, substantive: bool = False) -> Quote | None:
    if not text:
        return None
    try:
        q = find_quote(transcript, text)
    except QuoteNotFound:
        return None
    if substantive and transcript.segments and _is_housekeeping(q, transcript.segments[-1].end):
        return None
    return q


def main_speakers(transcript: Transcript, min_share: float = 0.05) -> list[str]:
    """Display names of speakers with at least `min_share` of the talk time, in order of
    appearance (diarization noise such as a two-word stray label is left out)."""
    talk: dict[str, float] = {}
    for seg in transcript.segments:
        talk[seg.speaker] = talk.get(seg.speaker, 0.0) + max(0.0, seg.end - seg.start)
    total = sum(talk.values()) or 1.0
    labels = [k for k in dict.fromkeys(s.speaker for s in transcript.segments)]
    keep = [k for k in labels if talk.get(k, 0) / total >= min_share] or labels[:1]
    return [transcript.speakers.get(k, f"Speaker {k}") for k in keep][:4]


def _cap_words(text: str, limit: int) -> str:
    """Trim to whole sentences within `limit` words (cover decks must fit their box)."""
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    cut = " ".join(words[:limit])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: end + 1] if end > 40 else cut.rstrip(",;:") + "\u2026").strip()


def _closing(book_chapters: list[Chapter], planned: Quote | None) -> Quote | None:
    if planned:
        return planned
    pulls = [b.quote for c in reversed(book_chapters) for b in c.blocks if isinstance(b, PullQuote)]
    return pulls[0] if pulls else None


def _assemble(plan: Plan, written: dict[tuple[int, int], Written], transcript, ctx) -> Book:
    segs = transcript.segments
    chapters = []
    for ci, cp in enumerate(plan.chapters):
        blocks: list[Block] = []
        for si, sp in enumerate(cp.sections):
            if si > 0 and sp.heading:
                blocks.append(Heading(sp.heading))
            blocks.extend(written[(ci, si)].blocks)
        opener = _verified(transcript, cp.opener, substantive=True) or next(
            (b.quote for b in blocks if isinstance(b, PullQuote)), None
        )
        chapters.append(
            Chapter(
                label=f"Part {LABELS[ci] if ci < len(LABELS) else ci + 1}",
                title=cp.title,
                dek=cp.dek,
                start=segs[cp.sections[0].first].start,
                end=segs[cp.sections[-1].last].end,
                opener=opener,
                blocks=blocks,
            )
        )
    title_accent = plan.title_accent if plan.title.endswith(plan.title_accent) else ""
    return Book(
        title=plan.title,
        title_accent=title_accent,
        deck=_cap_words(plan.deck, 45),
        podcast_title=ctx["podcast"],
        episode_number=int(ctx["number"]),
        episode_title=ctx["title"],
        speakers=main_speakers(transcript),
        duration=segs[-1].end,
        chapters=chapters,
        closing=_closing(chapters, _verified(transcript, plan.closing, substantive=True)),
        demo=ctx.get("demo") == "1",
    )


# --------------------------------------------------------------------- run / render


def _book_dir(book_row: BookRow, podcast: Podcast, episode: Episode) -> Path:
    d = storage.episode_dir(podcast, episode) / "books" / str(book_row.id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _artwork(podcast: Podcast) -> Path | None:
    """The podcast's artwork, downloaded once next to its episodes."""
    s = get_settings()
    if not podcast.image_url or s.download_mode == "fake":
        return None
    dst = s.podcasts_dir / podcast.slug / "artwork.img"
    if dst.is_file():
        return dst
    try:
        resp = httpx.get(podcast.image_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(resp.content)
        return dst
    except httpx.HTTPError:
        log.warning("book: could not download artwork for %s", podcast.title)
        return None


def render_book(book_id: int) -> BookRow:
    """(Re)render a written book with its current seed. No model calls."""
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        if row is None or not row.dir_path:
            raise ValueError(f"Book {book_id} has no written text yet")
        episode = session.get(Episode, row.episode_id)
        podcast = session.get(Podcast, episode.podcast_id) if episode else None
        if episode is None or podcast is None or not episode.transcript_path:
            raise ValueError("The episode for this book is missing")
        bdir = storage.to_abs(row.dir_path)
        seed = row.seed
        transcript = storage.read_transcript(storage.to_abs(episode.transcript_path))
    book = book_from_dict(json.loads((bdir / "book.json").read_text("utf-8")))
    theme = make_theme(seed)
    pdf = render_pdf(book, transcript.segments, theme, bdir / "book.pdf", artwork=_artwork(podcast))
    pages = _thumbnail(pdf, bdir / "cover.png")
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        assert row is not None
        row.family, row.art, row.pages = theme.family, theme.art, pages
        row.updated_at = utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def _thumbnail(pdf: Path, dst: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        page = doc[0]
        page.render(scale=640 / page.get_width()).to_pil().save(dst, "PNG", optimize=True)
        return len(doc)
    finally:
        doc.close()


def build_book(book_id: int, on_progress: ProgressFn) -> None:
    """Write and render a book (the "book" job)."""
    settings = get_settings()
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        if row is None:
            raise ValueError(f"Book {book_id} not found")
        episode = session.get(Episode, row.episode_id)
        podcast = session.get(Podcast, episode.podcast_id) if episode else None
        if episode is None or podcast is None:
            raise ValueError("Episode not found")
        if not episode.transcript_path:
            raise ValueError("Transcribe this episode before making a book")
        transcript = storage.read_transcript(storage.to_abs(episode.transcript_path))
        bdir = _book_dir(row, podcast, episode)
        row.status, row.dir_path, row.error = "writing", storage.to_rel(bdir), None
        session.add(row)
        session.commit()
        ctx = {
            "podcast": podcast.title,
            "number": str(episode.number),
            "title": episode.title,
            "description": episode.description or "",
            "demo": "1" if podcast.rss_url.startswith("demo://") else "0",
        }
    if not transcript.segments:
        raise ValueError("The transcript is empty")

    fake = settings.llm_provider == "fake"
    _, chapters, target = sizing(transcript)
    on_progress(0.02, "Planning chapters")
    started = time.monotonic()
    if fake:
        plan = _fake_plan(transcript, ctx, chapters)
    else:
        plan = _parse_plan(
            _ask_json(_plan_messages(transcript, ctx, chapters, target), max_tokens=12000),
            transcript,
            ctx,
        )
    _assign_targets(plan, transcript, target)
    (bdir / "plan.json").write_text(
        json.dumps(
            {
                "title": plan.title,
                "glossary": plan.glossary,
                "chapters": [
                    {"title": c.title, "sections": [s.__dict__ for s in c.sections]}
                    for c in plan.chapters
                ],
            },
            indent=1,
        ),
        "utf-8",
    )

    keys = [(ci, si) for ci, c in enumerate(plan.chapters) for si in range(len(c.sections))]
    written: dict[tuple[int, int], Written] = {}
    pool = ThreadPoolExecutor(max_workers=max(1, settings.book_parallelism))
    try:
        if fake:
            for k in keys:
                written[k] = _fake_section(plan, *k, transcript)
        else:
            pending = {pool.submit(_write_section, plan, *k, transcript, ctx): k for k in keys}
            while pending:
                done, _ = wait(pending, timeout=5.0, return_when=FIRST_COMPLETED)
                for fut in done:
                    written[pending.pop(fut)] = fut.result()
                elapsed = storage.fmt_ts(time.monotonic() - started)
                on_progress(
                    0.1 + 0.78 * len(written) / len(keys),
                    f"Writing: {len(written)}/{len(keys)} sections · {elapsed} elapsed",
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    book = _assemble(plan, written, transcript, ctx)
    (bdir / "book.json").write_text(json.dumps(book_to_dict(book), ensure_ascii=False), "utf-8")
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        assert row is not None
        row.title = book.title
        row.chapters = len(book.chapters)
        row.words = word_count(book)
        row.quotes = sum(w.quotes for w in written.values())
        row.rejected_quotes = sum(w.rejected for w in written.values())
        session.add(row)
        session.commit()

    on_progress(0.9, "Typesetting the PDF")
    render_book(book_id)
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        assert row is not None
        row.status = "ready"
        row.updated_at = utcnow()
        session.add(row)
        session.commit()
    on_progress(1.0, "Book ready")


def repair_book(book_id: int) -> BookRow:
    """Re-check an existing book with the current verifier and rules, then re-render.

    No model calls: recovers speaker words left unquoted in the narration, drops
    minor diarization labels from the credits, replaces housekeeping openers and
    closers, caps the cover deck. Text the writer produced is otherwise untouched.
    """
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        if row is None or not row.dir_path:
            raise ValueError(f"Book {book_id} has no written text yet")
        episode = session.get(Episode, row.episode_id)
        if episode is None or not episode.transcript_path:
            raise ValueError("The episode for this book is missing")
        bdir = storage.to_abs(row.dir_path)
        transcript = storage.read_transcript(storage.to_abs(episode.transcript_path))
    path = bdir / "book.json"
    book = book_from_dict(json.loads(path.read_text("utf-8")))
    duration = transcript.segments[-1].end if transcript.segments else 0.0
    quotes = 0
    for ch in book.chapters:
        for b in ch.blocks:
            if isinstance(b, Paragraph):
                b.runs = recover_hidden(transcript, b.runs)
                quotes += sum(1 for r in b.runs if isinstance(r, Quote))
        if ch.opener and _is_housekeeping(ch.opener, duration):
            ch.opener = next((b.quote for b in ch.blocks if isinstance(b, PullQuote)), None)
    if book.closing and _is_housekeeping(book.closing, duration):
        book.closing = _closing(book.chapters, None)
    book.speakers = main_speakers(transcript)
    book.deck = _cap_words(book.deck, 45)
    path.write_text(json.dumps(book_to_dict(book), ensure_ascii=False), "utf-8")
    with db.session_scope() as session:
        row = session.get(BookRow, book_id)
        assert row is not None
        pulls = sum(
            isinstance(b, PullQuote) + 2 * isinstance(b, QuotePair)
            for c in book.chapters
            for b in c.blocks
        )
        row.quotes, row.words = quotes + pulls, word_count(book)
        session.add(row)
        session.commit()
    return render_book(book_id)
