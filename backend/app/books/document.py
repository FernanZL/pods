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
