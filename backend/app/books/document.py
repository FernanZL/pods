"""The book as data: what the writer produces and the renderer lays out.

Text never carries raw speaker quotes. Quotes are `Quote` objects that the
verifier has matched word for word to a transcript segment, so every quotation
in the PDF is guaranteed to be real and correctly attributed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Quote:
    text: str  # verbatim words from the transcript
    speaker: str  # display name
    start: float  # seconds, start of the segment it came from


# A paragraph is a sequence of runs: plain narrative text or an inline quote.
Run = str | Quote


@dataclass
class Paragraph:
    runs: list[Run]


@dataclass
class Heading:
    text: str


@dataclass
class PullQuote:
    quote: Quote


@dataclass
class QuotePair:
    """Two short quotes side by side, e.g. host and guest on the same idea."""

    left: Quote
    right: Quote


@dataclass
class Callout:
    title: str
    items: list[str]


@dataclass
class SpeakerFigure:
    start: float
    end: float
    caption: str


Block = Paragraph | Heading | PullQuote | QuotePair | Callout | SpeakerFigure


@dataclass
class Chapter:
    label: str  # "Part one"
    title: str
    dek: str  # one-line standfirst
    start: float  # transcript window this chapter draws on (seconds)
    end: float
    opener: Quote | None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Book:
    title: str
    title_accent: str  # trailing words of the title set in the accent italic ("" for none)
    deck: str
    podcast_title: str
    episode_number: int
    episode_title: str
    speakers: list[str]  # display names in order of appearance
    duration: float  # seconds
    chapters: list[Chapter]
    closing: Quote | None
    demo: bool = False  # fictional demo content flag (printed on cover/colophon)
    narrator: str = ""  # speaker whose first-person voice tells the book ("" = narrator)
    tense: str = "past"  # "past" (looking back) | "present" (as it happens)


# --- (de)serialisation: book.json holds the written text, independent of design ---

_BLOCK_TYPES = {
    "p": Paragraph,
    "h": Heading,
    "pull": PullQuote,
    "pair": QuotePair,
    "callout": Callout,
    "fig": SpeakerFigure,
}
_TYPE_OF = {v: k for k, v in _BLOCK_TYPES.items()}


def _q(q: Quote | None) -> dict | None:
    return None if q is None else {"text": q.text, "speaker": q.speaker, "start": q.start}


def _uq(d: dict | None) -> Quote | None:
    return None if d is None else Quote(d["text"], d["speaker"], float(d["start"]))


def _block(b: Block) -> dict:
    t = _TYPE_OF[type(b)]
    if isinstance(b, Paragraph):
        return {"t": t, "runs": [r if isinstance(r, str) else _q(r) for r in b.runs]}
    if isinstance(b, Heading):
        return {"t": t, "text": b.text}
    if isinstance(b, PullQuote):
        return {"t": t, "quote": _q(b.quote)}
    if isinstance(b, QuotePair):
        return {"t": t, "left": _q(b.left), "right": _q(b.right)}
    if isinstance(b, Callout):
        return {"t": t, "title": b.title, "items": b.items}
    return {"t": t, "start": b.start, "end": b.end, "caption": b.caption}


def _unblock(d: dict) -> Block:
    t = d["t"]
    if t == "p":
        return Paragraph([r if isinstance(r, str) else _uq(r) for r in d["runs"]])
    if t == "h":
        return Heading(d["text"])
    if t == "pull":
        return PullQuote(_uq(d["quote"]))
    if t == "pair":
        return QuotePair(_uq(d["left"]), _uq(d["right"]))
    if t == "callout":
        return Callout(d["title"], list(d["items"]))
    return SpeakerFigure(float(d["start"]), float(d["end"]), d["caption"])


def book_to_dict(book: Book) -> dict:
    return {
        "title": book.title,
        "title_accent": book.title_accent,
        "deck": book.deck,
        "podcast_title": book.podcast_title,
        "episode_number": book.episode_number,
        "episode_title": book.episode_title,
        "speakers": book.speakers,
        "duration": book.duration,
        "closing": _q(book.closing),
        "demo": book.demo,
        "narrator": book.narrator,
        "tense": book.tense,
        "chapters": [
            {
                "label": c.label,
                "title": c.title,
                "dek": c.dek,
                "start": c.start,
                "end": c.end,
                "opener": _q(c.opener),
                "blocks": [_block(b) for b in c.blocks],
            }
            for c in book.chapters
        ],
    }


def book_from_dict(d: dict) -> Book:
    return Book(
        title=d["title"],
        title_accent=d.get("title_accent", ""),
        deck=d.get("deck", ""),
        podcast_title=d["podcast_title"],
        episode_number=int(d["episode_number"]),
        episode_title=d["episode_title"],
        speakers=list(d["speakers"]),
        duration=float(d["duration"]),
        closing=_uq(d.get("closing")),
        demo=bool(d.get("demo", False)),
        narrator=str(d.get("narrator") or ""),
        tense=str(d.get("tense") or "past"),
        chapters=[
            Chapter(
                label=c["label"],
                title=c["title"],
                dek=c["dek"],
                start=float(c["start"]),
                end=float(c["end"]),
                opener=_uq(c.get("opener")),
                blocks=[_unblock(b) for b in c["blocks"]],
            )
            for c in d["chapters"]
        ],
    )


def word_count(book: Book) -> int:
    n = 0
    for c in book.chapters:
        for b in c.blocks:
            if isinstance(b, Paragraph):
                n += sum(len((r if isinstance(r, str) else r.text).split()) for r in b.runs)
    return n
