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
from app.services.artwork import artwork_path
from app.services.uploads import show_label

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

_VOICE_NARRATOR = """Editorial preset: MAGAZINE FEATURE (long-form).
- Voice: a sharp, warm feature writer narrating in the third person about the conversation.
  The narrator is NOT the speakers: never write in a speaker's first person, never invent
  what they think, never put words in their mouths."""

_VOICE_FIRST_PERSON = """Editorial preset: FIRST-PERSON RETELLING (long-form).
- Voice: {name}, the {role} of this episode, tells the story of this conversation in the
  first person ("I", "me", "my"), {frame}. Everyone else ({others}) appears in the third
  person, by name.
- My side of the story comes ONLY from {name}'s own lines in the transcript: what I asked,
  said, argued, shared or reacted to. Never invent memories, feelings, scenes, settings,
  backstory or opinions that {name} did not voice in this conversation.
- Credit every idea to whoever said it. A point another speaker makes is theirs ("{other}
  argues that..."), never "I". A point I make in the episode can be told in my voice."""

_FRAME = {
    "past": "looking back on it as a long-form essay",
    "present": "living it as it happens, in the present tense",
}

_TENSE_PRESENT = """\
- Tense: PRESENT, live. Tell the conversation as it unfolds, moment by moment, so the
  reader is in the room while it happens, the way watching the episode feels: "{example}"
  Speech is reported in the present ("says", "asks", "pushes back", "laughs it off").
- Nothing is known ahead of time: no hindsight or foreshadowing ("later", "would go on to",
  "as it turned out", "looking back", "I remember", "that day"). What comes later in the
  talk has not happened yet; let each turn land as it arrives.
- The present tense comes from the telling, not from invented stage business: no gestures,
  looks, rooms, clothes or weather that the conversation itself does not show."""

_STYLE_BODY = """\
- Story-driven: open sections with a concrete moment, question or tension from the talk;
  follow the argument as it develops; keep the examples, stories, numbers, caveats and
  disagreements that make it real. Explain technical ideas plainly without dumbing down.
- Long, not padded: cover everything substantive in the slice in the order it matters.
  Cut repetition, ad reads, sponsor segments, housekeeping and filler. Do not summarise
  the section at its end and do not moralise.
- Rhythm: vary sentence length; short paragraphs (2-5 sentences); concrete verbs; no lists
  inside paragraphs.
- British or American spelling consistently (follow the transcript)."""

_VOICE_AUTHOR = """Editorial preset: THE AUTHOR'S OWN BOOK (long-form non-fiction).
- This is {name}'s own book, written by {name} for the reader. {name} writes in the first
  person ("I") and talks to the reader directly ("you"), the way an author writes the book
  they are known for: teaching, explaining, arguing, telling their stories and examples.
- The recording is raw material, never the story. Do not report it: no "I said", "I asked",
  "I told", "I began by", "I explained", "I described", "as I put it", "I mentioned", "in this
  episode / lecture / video / talk / conversation", "today", "my guest", "the audience",
  "listeners", "viewers", "members", "chat". State the ideas as the author's own claims:
  "The ego is a story the mind tells about itself", never "I said the ego is...".
- Sound like {name}: their vocabulary, their kinds of examples, their humour and directness,
  their recurring phrases, as their lines show them. Polished for the page: no filler,
  false starts or verbal tics of speech.
- All substance comes from the transcript: the ideas, explanations, examples, stories,
  numbers, studies, caveats and practical steps. You may connect, explain plainly, ask the
  reader questions and speak to their experience ("you have probably felt this"), but never
  add facts, studies, stories, memories or advice that nobody in the recording gave.
{others_rule}"""

_AUTHOR_OTHERS = """\
- {others} {appear} the author learned from, by name and with credit, the way a
  non-fiction author cites someone they interviewed: "{other} has a way of putting this:
  ⟦...⟧", "When I sat down with {other}, ...". Their ideas stay theirs, never told as "I";
  their best lines are quoted verbatim. Mentioning that you talked with {other} is fine, but
  the conversation is never the frame of a chapter.
- When most of the substance comes from {other}, the book is {name} presenting {other}'s
  ideas with credit, plus {name}'s own explanations and comments. A question {name} asked
  becomes the question the section explores ("So why would anyone ...?"), not "I asked"."""

_AUTHOR_SOLO = """\
- {name} is the only voice: the whole book is theirs, with no one else to credit."""

_STYLE_BOOK = """\
- Teach, don't recap: open each section with a hook the author would use (a question, a
  case, a striking claim, a story they tell), build the argument step by step, and land the
  point for the reader's own life. Keep the examples, stories, numbers, caveats and nuance
  that make it real. Explain technical ideas plainly without dumbing down.
- Long, not padded: cover everything substantive in the slice. Cut repetition, ad reads,
  sponsor segments, housekeeping, audience Q&A logistics and filler. Do not summarise the
  section at its end and do not moralise beyond what the author says.
- Rhythm: vary sentence length; short paragraphs (2-5 sentences); concrete verbs; no lists
  inside paragraphs.
- British or American spelling consistently (follow the transcript)."""

_QUOTING = """Quoting rules (strict, checked by code against the transcript):
- Wrap every verbatim quote in ⟦ and ⟧ inside paragraph text, e.g. as she puts it, ⟦the
  morning sets the clock⟧. Copy the words EXACTLY from the transcript slice (5-30 words, one
  contiguous passage, no ellipses, no edits). Attribution comes from the transcript, so
  say who is speaking in your own words around the quote.
- Use 2-5 inline quotes per section, plus at most one "pull" quote (a striking line, 8-30
  words, also verbatim). Quotes that do not match the transcript exactly are removed."""

_QUOTING_FIRST_PERSON = """
- Quote mostly the other speakers. My own lines are usually told in my voice rather than
  quoted; when one is worth quoting, frame it as mine (as I put it, ⟦...⟧)."""


_QUOTING_AUTHOR = """Quoting rules (strict, checked by code against the transcript):
- The author's own lines are the prose: rewrite them as written text, never quote them in a
  paragraph and never frame them as speech ("as I said", "as I put it").
- Other speakers are quoted verbatim: wrap the words in ⟦ and ⟧ inside paragraph text, e.g.
  as Robert puts it, ⟦the morning sets the clock⟧. Copy EXACTLY from the transcript slice
  (5-30 words, one contiguous passage, no ellipses, no edits) and say who it is around it.
  Use 0-4 such quotes per section; none when no one else speaks in the slice.
- At most one "pull" quote per section: a striking verbatim line (8-30 words), which may be
  the author's own. Quotes that do not match the transcript exactly are removed."""


def present_tense(ctx: dict[str, str]) -> bool:
    return ctx.get("tense") == "present"


def authored(ctx: dict[str, str]) -> bool:
    """The speaker's own book (form "book"), rather than a retelling of the conversation."""
    return ctx.get("form") == "book" and bool(ctx.get("narrator"))


def style(ctx: dict[str, str]) -> str:
    """Editorial style for the book's voice: a third-person narrator, or a speaker in the
    first person (ctx["narrator"] is that speaker's display name), told looking back
    (ctx["tense"] "past", the default) or as it happens ("present")."""
    name = ctx.get("narrator", "")
    if authored(ctx):
        others = [s for s in ctx.get("speakers", "").split("|") if s and s != name]
        others_rule = (
            _AUTHOR_OTHERS.format(
                name=name,
                others=" and ".join(others),
                other=others[0].split()[0],
                appear="appear as people" if len(others) > 1 else "appears as someone",
            )
            if others
            else _AUTHOR_SOLO.format(name=name)
        )
        return f"{_VOICE_AUTHOR.format(name=name, others_rule=others_rule)}\n{_STYLE_BOOK}"
    present = present_tense(ctx)
    if not name:
        voice = _VOICE_NARRATOR
        example = "Where does it start, the host asks. The guest has an answer ready: ..."
    else:
        others = [s for s in ctx.get("speakers", "").split("|") if s and s != name]
        other = others[0].split()[0] if others else "My guest"
        voice = _VOICE_FIRST_PERSON.format(
            name=name,
            role=ctx.get("narrator_role") or "host",
            others=" and ".join(others) or "the other speakers",
            other=other,
            frame=_FRAME["present" if present else "past"],
        )
        example = f"Where does it start, I ask. {other} has an answer ready: ..."
    if present:
        voice += "\n" + _TENSE_PRESENT.format(example=example)
    return f"{voice}\n{_STYLE_BODY}"


def quoting(ctx: dict[str, str]) -> str:
    if authored(ctx):
        return _QUOTING_AUTHOR
    return _QUOTING + (_QUOTING_FIRST_PERSON if ctx.get("narrator") else "")


# ---------------------------------------------------------------------------- titles

_TITLE_TAGS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_TITLE_NUMBER = re.compile(r"^\s*(#\s*\d+|ep(isode)?\.?\s*\d+)\s*[:\-\u2013\u2014|.]*\s*", re.I)
_TITLE_STOP = frozenset(
    {"the", "and", "for", "with", "your", "you", "our", "how", "why", "what", "from", "into"}
)


def clean_title(title: str) -> str:
    """The episode title tidied for a cover: no bracketed tags, episode numbers, or a
    guest name after " | " (the longest part is kept)."""
    t = _TITLE_NUMBER.sub("", _TITLE_TAGS.sub("", title))
    parts = [p.strip() for p in re.split(r"\s+[|\u2013\u2014]\s+|\s+-\s+", t) if p.strip()]
    t = max(parts, key=len) if parts else t
    return t.strip(" .,:;-|\u2013\u2014") or title.strip()


def _title_stems(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w[:5] for w in words if len(w) > 2 and w not in _TITLE_STOP}


def pick_title(proposed: str, episode_title: str) -> str:
    """The planner's title when it keeps to the episode's own words (a tidied version of
    it), otherwise the cleaned episode title: a book is never renamed into something new."""
    proposed = proposed.strip().strip('"')
    stems, source = _title_stems(proposed), _title_stems(episode_title)
    if stems and source and len(stems & source) / len(stems) >= 0.75:
        return proposed
    return clean_title(episode_title)


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
    # plan + section slices + prompts, then the editor (book + transcript) and ~20% rewrites
    tok_in = words * 1.35 * 2 + 3000 + 1800 * chapters * 3
    tok_in += (words + target) * 1.35 + 3000 + 0.2 * (words * 1.35 + 1800 * chapters * 3)
    tok_out = 4000 + target * 1.45 + 3000 + 0.2 * target * 1.45
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


def _source(ctx: dict[str, str]) -> str:
    if ctx.get("podcast"):
        return f"Podcast: {ctx['podcast']}, episode {ctx['number']}: {ctx['title']}"
    return f"Recording (an uploaded audio file): {ctx['title']}"


def _plan_messages(transcript: Transcript, ctx: dict[str, str], chapters: int, target: int):
    n = len(transcript.segments)
    if authored(ctx):
        intro = (
            f"You are the editor planning {ctx['narrator']}'s own long-form non-fiction book,"
            f" built from one recording of {ctx['narrator']}. It is not a retelling of the"
            " recording: it teaches its ideas the way a book by the author would. It is long"
            " and complete, NOT a summary."
        )
        arcs = (
            "- Chapters are the book's argument: each is built around one idea and titled by"
            " it, never by a moment in the recording. Keep the recording's order (sections"
            " must be contiguous), choosing chapter breaks where the ideas change.\n"
            "- Title, deck and deks never mention the episode, the recording, the host, the"
            " guest or the conversation; the deck is the book's back-cover line in the"
            " author's voice."
        )
    else:
        intro = (
            "You are the editor planning a long-form magazine-style book from one podcast\n"
            "episode. The book retells the conversation as narrative non-fiction: it is long"
            " and complete,\nNOT a summary."
        )
        arcs = "- Chapters follow the conversation's real arcs, not equal time slices."
    system = f"""{intro}

Return ONLY a JSON object:
{{
  "title": "the episode's own title, tidied for a book cover (see rules)",
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
{arcs}
- The title is NOT a new invention: it is the episode's own title, tidied for a cover. Keep
  its key words; drop the show name, episode numbers, a guest name after "|" or "-",
  bracketed tags like "(Free Members Lecture)" and presenter lead-ins like "Dr K Explains".
  E.g. "Access the Sublime & Live Your Best Life | Robert Greene" -> "Access the Sublime &
  Live Your Best Life"; "Dr K. Explains Escaping Your Ego (Free Members Lecture)" ->
  "Escaping Your Ego".
- Quotes must be copied exactly from the transcript.
- Title, deck and every dek are in the same voice as the book (see the style below).
- Opener and closing quotes must be substantive lines from the conversation itself: never
  the intro, the outro, thanks, sponsor reads, or requests to subscribe/follow/review.
- The whole book will be about {target} words.
{style(ctx)}"""
    user = (
        f"{_source(ctx)}\n"
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
        title=pick_title(str(data.get("title") or ""), ctx["title"]),
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
    if authored(ctx):
        role = (
            f"You are ghost-writing one section of {ctx['narrator']}'s own non-fiction book,"
            f" built from a recording of {ctx['narrator']}."
        )
        callout = '"Try this: ..."'
    else:
        role = (
            "You are writing one section of a long-form book that retells a podcast\n"
            "conversation as narrative non-fiction."
        )
        callout = '"From the episode: ..."'
    system = f"""{role}

{style(ctx)}

{quoting(ctx)}

Never use these words or phrases: {banned}.

Return ONLY a JSON object:
{{"blocks": [
  {{"type": "p", "text": "paragraph with ⟦verbatim quotes⟧"}},
  {{"type": "pull", "quote": "verbatim striking line"}},
  {{"type": "pair", "left": "verbatim line", "right": "verbatim reply"}},
  {{"type": "callout", "title": {callout}, "items": ["practical step", "..."]}}
]}}
- Mostly "p" blocks. "pull" at most once, roughly mid-section. "pair" only for a real
  back-and-forth exchange (both lines verbatim). "callout" only when the slice gives concrete,
  practical steps (3-5 short items, paraphrased, no invented advice); at most one per section.
- Length: about {sec.target_words} words of paragraph text. Do not stop short; do not pad.
- No headings (the section heading is set by the layout). Do not repeat earlier sections.
- Never narrate the show's own housekeeping: sponsors and ads, links, "subscribe", "follow",
  "leave a review", thanks for listening, intros and outros. If the slice ends with the
  outro, end the section on the last substantive idea instead.
- The reader sees only the book. Never mention the transcript, the slice, an excerpt,
  segments or the recording, and never say where they start or stop ("the transcript ends
  before..."). If the slice stops mid-thought, end on its last complete idea."""
    user = (
        f"Book: {plan.title}\n{_source(ctx)}\nChapter {ci + 1}: {ch.title} ({ch.dek})\n"
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


def _to_blocks(data: dict[str, Any], transcript: Transcript, own: str = "") -> Written:
    blocks: list[Block] = []
    quotes = rejected = 0
    pulls = callouts = 0
    for raw in data.get("blocks") or []:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type")
        try:
            if kind == "p" and str(raw.get("text") or "").strip():
                runs, bad = resolve_runs(transcript, str(raw["text"]).strip(), own)
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
    return _to_blocks(data, transcript, ctx.get("narrator", ""))


# ----------------------------------------------------------------------- editor


def _section_text(w: Written) -> str:
    """Readable draft of a section: quotes inline with their (verified) attribution."""
    out = []
    for b in w.blocks:
        if isinstance(b, Paragraph):
            out.append(
                "".join(
                    r
                    if isinstance(r, str)
                    else f"\u201c{r.text}\u201d [{r.speaker} {_ts(r.start)}]"
                    for r in b.runs
                )
            )
        elif isinstance(b, PullQuote):
            out.append(f"PULL QUOTE: \u201c{b.quote.text}\u201d [{b.quote.speaker}]")
        elif isinstance(b, QuotePair):
            out.append(f"PAIR: \u201c{b.left.text}\u201d / \u201c{b.right.text}\u201d")
        elif isinstance(b, Callout):
            out.append(f"CALLOUT {b.title}: " + "; ".join(b.items))
    return "\n\n".join(out)


def _review_messages(plan: Plan, written: dict[tuple[int, int], Written], transcript, ctx):
    name = ctx.get("narrator", "")
    voice_rule = (
        f'\nThe narration is in the first person as {name}: everything "I" said, asked, thought'
        f" or did must come from {name}'s own lines. Report first-person memories, feelings,"
        f" opinions or scenes {name} never voiced as off_topic, and another speaker's idea told"
        ' as "I" as misattribution.'
        if name
        else ""
    )
    if authored(ctx):
        voice_rule = (
            f"\nThe book is written as {name}'s own book, in the first person, to the reader."
            " Report narration that reports the recording instead of teaching its ideas"
            ' ("I said", "I asked", "I explained", "as I put it", "in this episode / lecture /'
            ' video", "my guest", "the audience") as housekeeping; facts, studies, stories,'
            f" memories or advice that nobody in the recording gave as off_topic; and another"
            f" speaker's idea told as {name}'s own as misattribution."
        )
    elif present_tense(ctx):
        voice_rule += (
            "\nThe book is told in the present tense, as the conversation happens; that is"
            ' intended. Report hindsight that gives away later parts of the talk ("later",'
            ' "would go on to") and invented gestures or scenery as off_topic.'
        )
    system = f"""You are the fact-checking editor of a long-form book written from a podcast
conversation. Quotes in the draft have already been verified word for word; your job is the
NARRATION around them. Compare every section with the transcript and report only real
problems:
- misattribution: an idea, claim or story credited to the wrong person
- factual: numbers, names, dates, mechanisms or details that differ from what was said
- overstatement: a claim stated more strongly or generally than the speaker made it
- repetition: a point substantially repeated from an earlier section
- housekeeping: sponsors, ads, links, "subscribe", intros/outros narrated as content, or
  narration about the source itself ("the transcript", "the excerpt", where it ends)
- off_topic: content not in this section's transcript range, or invented material
Do not report style preferences. Cite transcript evidence by segment number.{voice_rule}

Return ONLY JSON:
{{"summary": "one or two sentences on overall accuracy",
 "issues": [{{"section": "3.2", "type": "misattribution|factual|overstatement|repetition|
   housekeeping|off_topic", "severity": "high|medium|low", "problem": "what is wrong",
   "evidence": "[segment numbers] and the words that show it", "fix": "what the corrected
   text must say"}}]}}
Use an empty list when the book is accurate."""
    parts = []
    for ci, ch in enumerate(plan.chapters):
        for si, sec in enumerate(ch.sections):
            parts.append(
                f"## {ci + 1}.{si + 1} {ch.title} / {sec.heading} (segments {sec.first}-{sec.last})"
                f"\n{_section_text(written[(ci, si)])}"
            )
    user = (
        f"Book: {plan.title}\n{_source(ctx)}"
        "\n\nDRAFT BOOK:\n" + "\n\n".join(parts) + "\n\nTRANSCRIPT:\n" + _numbered(transcript)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _rewrite_section(
    plan: Plan, ci: int, si: int, transcript: Transcript, ctx, draft: Written, notes: list[dict]
) -> Written:
    msgs = _section_messages(plan, ci, si, transcript, ctx)
    issues = "\n".join(
        f"- [{n.get('type')}] {n.get('problem')} Evidence: {n.get('evidence')}. Fix: {n.get('fix')}"
        for n in notes
    )
    msgs[1]["content"] += (
        f"\n\nPREVIOUS DRAFT OF THIS SECTION:\n{_section_text(draft)}\n\n"
        "EDITOR'S NOTES - rewrite the section fixing every note, keep everything that is "
        f"correct, keep the same length and quoting rules:\n{issues}"
    )
    sec = plan.chapters[ci].sections[si]
    data = _ask_json(msgs, max_tokens=int(sec.target_words * 2.2) + 1500)
    return _to_blocks(data, transcript, ctx.get("narrator", ""))


def _words(w: Written) -> int:
    return sum(
        len((r if isinstance(r, str) else r.text).split())
        for b in w.blocks
        if isinstance(b, Paragraph)
        for r in b.runs
    )


@dataclass
class Review:
    summary: str
    issues: list[dict[str, Any]]
    fixed_sections: list[str]


def _editor(
    plan: Plan,
    written: dict[tuple[int, int], Written],
    transcript: Transcript,
    ctx: dict[str, str],
    pool: ThreadPoolExecutor,
    on_progress: ProgressFn,
) -> Review:
    """Review the narration against the transcript; rewrite flagged sections once."""
    try:
        data = _ask_json(_review_messages(plan, written, transcript, ctx), max_tokens=8000)
    except Exception as exc:  # the editor improves a book; it must not sink it
        log.warning("book editor unavailable: %s", exc)
        return Review(f"Editor unavailable: {exc}", [], [])
    keys = {f"{ci + 1}.{si + 1}": (ci, si) for ci, si in written}
    issues = [
        i for i in (data.get("issues") or [])
        if isinstance(i, dict) and str(i.get("section")) in keys
    ]  # fmt: skip
    by_section: dict[tuple[int, int], list[dict]] = {}
    for issue in issues:
        if issue.get("severity") in ("high", "medium"):
            by_section.setdefault(keys[str(issue["section"])], []).append(issue)
    fixed: list[str] = []
    if by_section:
        on_progress(0.86, f"Editor: fixing {len(by_section)} sections")
        futures = {
            pool.submit(_rewrite_section, plan, *k, transcript, ctx, written[k], notes): k
            for k, notes in by_section.items()
        }
        for fut, k in futures.items():
            try:
                new = fut.result()
            except Exception as exc:
                log.warning("book editor: rewrite of %s failed: %s", k, exc)
                continue
            # keep the rewrite only if it did not collapse the section
            if _words(new) >= 0.6 * _words(written[k]):
                written[k] = new
                fixed.append(f"{k[0] + 1}.{k[1] + 1}")
    for issue in issues:
        issue["fixed"] = str(issue.get("section")) in fixed
    return Review(str(data.get("summary") or ""), issues, fixed)


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
        title=clean_title(ctx["title"]),
        title_accent="",
        deck=ctx["description"][:200],
        closing=" ".join(segs[-1].text.split()[:12]),
        glossary=[],
        chapters=plan_chapters,
    )


def _fake_section(
    plan: Plan, ci: int, si: int, transcript: Transcript, narrator: str = ""
) -> Written:
    sec = plan.chapters[ci].sections[si]
    blocks: list[Block] = []
    for i in range(sec.first, sec.last + 1):
        s = transcript.segments[i]
        name = transcript.speakers.get(s.speaker, s.speaker)
        words = s.text.split()
        if len(words) < 6:
            continue
        quote = " ".join(words[:10])
        if narrator and name == narrator:
            text = f"At {_ts(s.start)}, I pick up the thread: as I put it, ⟦{quote}⟧."
        else:
            text = f"At {_ts(s.start)}, {name} picks up the thread: ⟦{quote}⟧."
        runs, _ = resolve_runs(transcript, text, narrator)
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


def main_labels(transcript: Transcript, min_share: float = 0.05) -> list[str]:
    """Labels of speakers with at least `min_share` of the talk time, in order of
    appearance (diarization noise such as a two-word stray label is left out)."""
    talk: dict[str, float] = {}
    for seg in transcript.segments:
        talk[seg.speaker] = talk.get(seg.speaker, 0.0) + max(0.0, seg.end - seg.start)
    total = sum(talk.values()) or 1.0
    labels = [k for k in dict.fromkeys(s.speaker for s in transcript.segments)]
    keep = [k for k in labels if talk.get(k, 0) / total >= min_share] or labels[:1]
    return keep[:4]


def main_speakers(transcript: Transcript, min_share: float = 0.05) -> list[str]:
    """Display names of the main speakers (see `main_labels`)."""
    return [_name(transcript, k) for k in main_labels(transcript, min_share)]


def _name(transcript: Transcript, label: str) -> str:
    return transcript.speakers.get(label, f"Speaker {label}")


def host_label(transcript: Transcript, podcast_title: str) -> str | None:
    """Best guess at the host among the main speakers: the one named in the podcast's
    title ("Huberman Lab"), otherwise the one who asks the most questions."""
    labels = main_labels(transcript)
    if not labels:
        return None
    title_words = set(re.findall(r"[a-z]+", podcast_title.lower()))
    for label in labels:
        name = _name(transcript, label)
        if name.lower().startswith("speaker "):
            continue
        if any(len(w) > 2 and w in title_words for w in re.findall(r"[a-z]+", name.lower())):
            return label
    questions = {k: 0 for k in labels}
    for seg in transcript.segments:
        if seg.speaker in questions:
            questions[seg.speaker] += seg.text.count("?")
    return max(labels, key=lambda k: questions[k])


def speaker_roles(transcript: Transcript, podcast_title: str) -> list[tuple[str, str, str]]:
    """(label, display name, "host" | "guest") for each main speaker, host first."""
    host = host_label(transcript, podcast_title)
    roles = [
        (k, _name(transcript, k), "host" if k == host else "guest") for k in main_labels(transcript)
    ]
    return sorted(roles, key=lambda r: r[2] != "host")


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
        narrator=ctx.get("narrator", ""),
        tense=ctx.get("tense", "past"),
        form="book" if authored(ctx) else "retelling",
    )


# --------------------------------------------------------------------- run / render


def _book_dir(book_row: BookRow, podcast: Podcast, episode: Episode) -> Path:
    d = storage.episode_dir(podcast, episode) / "books" / str(book_row.id)
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    art = artwork_path(podcast)
    pdf = render_pdf(book, transcript.segments, theme, bdir / "book.pdf", artwork=art)
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
            "podcast": show_label(podcast),
            "number": str(episode.number),
            "title": episode.title,
            "description": episode.description or "",
            "demo": "1" if podcast.rss_url.startswith("demo://") else "0",
            "narrator": row.narrator or "",
            "tense": "present" if row.tense == "present" else "past",
            "form": "book" if row.form == "book" else "retelling",
        }
    roles = speaker_roles(transcript, podcast.title)
    ctx["speakers"] = "|".join(name for _, name, _ in roles)
    ctx["narrator_role"] = next((r for _, n, r in roles if n == ctx["narrator"]), "host")
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
                written[k] = _fake_section(plan, *k, transcript, ctx.get("narrator", ""))
        else:
            pending = {pool.submit(_write_section, plan, *k, transcript, ctx): k for k in keys}
            while pending:
                done, _ = wait(pending, timeout=5.0, return_when=FIRST_COMPLETED)
                for fut in done:
                    written[pending.pop(fut)] = fut.result()
                elapsed = storage.fmt_ts(time.monotonic() - started)
                on_progress(
                    0.1 + 0.68 * len(written) / len(keys),
                    f"Writing: {len(written)}/{len(keys)} sections · {elapsed} elapsed",
                )
        if fake:
            review = Review("Editor skipped in demo mode.", [], [])
        else:
            on_progress(0.8, "Editor checking the narration against the transcript")
            review = _editor(plan, written, transcript, ctx, pool, on_progress)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    (bdir / "review.json").write_text(
        json.dumps(
            {"summary": review.summary, "fixed_sections": review.fixed_sections,
             "issues": review.issues},
            ensure_ascii=False, indent=1,
        ),
        "utf-8",
    )  # fmt: skip

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
        row.review_issues = len(review.issues)
        row.review_fixed = sum(1 for i in review.issues if i.get("fixed"))
        row.review_summary = review.summary[:600]
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

    No model calls: retitles a book whose title strays from the episode's, recovers speaker
    words left unquoted in the narration, drops
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
        episode_title = episode.title
    path = bdir / "book.json"
    book = book_from_dict(json.loads(path.read_text("utf-8")))
    title = pick_title(book.title, episode_title)  # an invented title becomes the episode's
    if title != book.title:
        book.title = title
        book.title_accent = book.title_accent if title.endswith(book.title_accent) else ""
    duration = transcript.segments[-1].end if transcript.segments else 0.0
    quotes = 0
    for ch in book.chapters:
        for b in ch.blocks:
            if isinstance(b, Paragraph):
                b.runs = recover_hidden(transcript, b.runs, book.narrator)
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
        row.quotes, row.words, row.title = quotes + pulls, word_count(book), book.title
        session.add(row)
        session.commit()
    return render_book(book_id)
