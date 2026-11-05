"""Book -> HTML -> PDF. Deterministic: the same Book, segments and theme give the same PDF."""

from __future__ import annotations

import html
from collections.abc import Sequence
from pathlib import Path

from app.books.art import art_markup, duotone
from app.books.document import (
    Book,
    Callout,
    Chapter,
    Heading,
    Paragraph,
    PullQuote,
    Quote,
    QuotePair,
    SpeakerFigure,
)
from app.books.tapes import tapes_svg
from app.books.theme import STATIC_DIR, Theme
from app.domain import Segment

CSS_PATH = Path(__file__).parent / "book.css"
CONTENT_W = 164.0  # mm, page content box
COLUMN_W = 124.0  # mm, reading column


def _ts(sec: float) -> str:
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _e(text: str) -> str:
    return html.escape(text, quote=False)


def _theme_css(theme: Theme) -> str:
    p = theme.palette
    f = theme.fonts

    def faces(family: str, stem: str, weights: tuple[int, ...], style: str = "normal") -> str:
        """One static file per weight; WeasyPrint does not reliably pick variable weights."""
        rules = []
        for w in weights:
            url = (STATIC_DIR / f"{stem}-{w}.ttf").as_uri()
            rules.append(
                f'@font-face {{ font-family: "{family}"; src: url("{url}"); '
                f"font-weight: {w}; font-style: {style}; }}"
            )
        return "\n".join(rules)

    return "\n".join(
        [
            faces("Book Serif", f.serif, (400, 600, 700)),
            faces("Book Serif", f.serif_italic, (400, 600), "italic"),
            faces("Book Sans", f.sans, (400, 600, 700)),
            ":root {",
            '  --serif: "Book Serif"; --sans: "Book Sans";',
            f"  --display-weight: {f.display_weight}; --display-tracking: {f.display_tracking};",
            f"  --ink: {p.ink}; --ink-muted: {p.ink_muted}; --paper: {p.paper};",
            f"  --primary: {p.primary}; --primary-ink: {p.primary_ink};",
            f"  --primary-soft: {p.primary_soft};",
            f"  --accent: {p.accent}; --accent2: {p.accent2}; --accent-light: {p.accent_light};",
            f"  --tint: {p.tint}; --tint2: {p.tint2}; --line: {p.line};",
            "}",
        ]
    )


class _Notes:
    """Collects every quote used, for the sources table."""

    def __init__(self) -> None:
        self.quotes: dict[tuple[str, float], Quote] = {}

    def add(self, q: Quote) -> Quote:
        self.quotes[(q.text, q.start)] = q
        return q


def _inline(q: Quote, notes: _Notes, book: Book) -> str:
    notes.add(q)
    return (
        f'<q class="said">{_e(q.text)}</q>'
        f'<span class="fn"><b>{_e(q.speaker)}</b>, {_ts(q.start)}. '
        f"{_e(book.podcast_title)}, episode {book.episode_number}.</span>"
    )


def _paragraph(par: Paragraph, notes: _Notes, book: Book, dropcap: bool) -> str:
    parts: list[str] = []
    for i, run in enumerate(par.runs):
        if isinstance(run, Quote):
            parts.append(_inline(run, notes, book))
            continue
        text = _e(run)
        if dropcap and i == 0 and text[:1].isalpha():
            text = f'<span class="dropcap">{text[0]}</span>{text[1:]}'
        parts.append(text)
    return f"<p>{''.join(parts)}</p>"


def _cite(q: Quote) -> str:
    return f"<cite>{_e(q.speaker)} &middot; {_ts(q.start)}</cite>"


def _chapter(
    ch: Chapter, idx: int, book: Book, segs: Sequence[Segment], theme: Theme, notes: _Notes
) -> str:
    p = theme.palette
    strip = ""
    if theme.opener_art == "echo":
        kind = theme.fallback_art if theme.art == "image" else theme.art
        height = 6 if kind == "field" else 15
        strip = art_markup(
            kind, segs, ch.start, ch.end, CONTENT_W, height, theme, salt=idx + 1, rows=3
        )
    head = (
        f'<div class="opener-head"><div class="opener-label">{_e(ch.label)}</div>'
        f'<h2>{_e(ch.title)}</h2><p class="dek">{_e(ch.dek)}</p></div>'
    )
    opener_q = ""
    if ch.opener:
        notes.add(ch.opener)
        opener_q = (
            f'<p class="opener-quote">&#8220;{_e(ch.opener.text)}&#8221;{_cite(ch.opener)}</p>'
        )
    out = [
        f'<section class="chapter" id="ch{idx + 1}"><div class="opener">{head}'
        f'<div class="opener-tapes">{strip}</div>{opener_q}</div><div class="col">'
    ]
    first_par = True
    for block in ch.blocks:
        if isinstance(block, Paragraph):
            out.append(_paragraph(block, notes, book, theme.dropcap and first_par))
            first_par = False
        elif isinstance(block, Heading):
            out.append(f'<h3 class="section">{_e(block.text)}</h3>')
        elif isinstance(block, PullQuote):
            notes.add(block.quote)
            out.append(
                f'</div><blockquote class="pull wide"><p>&#8220;{_e(block.quote.text)}&#8221;</p>'
                f'{_cite(block.quote)}</blockquote><div class="col">'
            )
        elif isinstance(block, QuotePair):
            notes.add(block.left)
            notes.add(block.right)
            out.append(
                '</div><div class="pair wide">'
                + "".join(
                    f"<figure><p>&#8220;{_e(q.text)}&#8221;</p>{_cite(q)}</figure>"
                    for q in (block.left, block.right)
                )
                + '</div><div class="col">'
            )
        elif isinstance(block, Callout):
            items = "".join(f"<li>{_e(i)}</li>" for i in block.items)
            out.append(f'<div class="callout"><h4>{_e(block.title)}</h4><ol>{items}</ol></div>')
        elif isinstance(block, SpeakerFigure):
            fig = tapes_svg(
                segs,
                block.start,
                block.end,
                rows=1,
                width=CONTENT_W,
                height=7,
                colors=p.speakers,
                style=theme.tape_style,
                seed=theme.seed,
            )
            out.append(
                f'</div><figure class="figure wide">{fig}<figcaption>{block.caption}</figcaption>'
                '</figure><div class="col">'
            )
    out.append(f'<div class="ending">End of {_e(ch.label.lower())}</div></div></section>')
    return "".join(out)


COVER_ART_SIZE = {"band": (210, 96), "panel": (178, 46), "column": (210, 92)}  # mm


def _cover(book: Book, segs: Sequence[Segment], theme: Theme, image_uri: str | None = None) -> str:
    layout = theme.cover_layout
    title = _e(book.title)
    if book.title_accent and book.title.endswith(book.title_accent):
        head = _e(book.title[: -len(book.title_accent)])
        title = f"{head}<em>{_e(book.title_accent)}</em>"
    masthead = (
        f'<div class="cover-masthead"><b>Pods</b><span>{_e(book.podcast_title)} &middot; '
        f"Episode {book.episode_number}</span></div>"
    )
    w, h = COVER_ART_SIZE[layout]
    tapes = art_markup(theme.art, segs, 0, book.duration, w, h, theme, image_uri=image_uri)
    foot = (
        f'<div class="cover-foot"><span>{_e(" & ".join(book.speakers))} &middot; '
        f"{_ts(book.duration)} of conversation</span>"
        f"<span>{'Fictional demo content' if book.demo else 'Made with Pods'}</span></div>"
    )
    title_el = f'<h1 class="cover-title">{title}</h1>'
    deck = f'<p class="cover-deck">{_e(book.deck)}</p>'
    tapes_el = f'<div class="cover-tapes">{tapes}</div>'
    if layout == "panel":
        inner = f'<div class="cover-box">{masthead}{title_el}</div>{tapes_el}{deck}'
    elif layout == "column":
        inner = f'{masthead}{title_el}<div class="cover-rule"></div>{deck}{tapes_el}'
    else:
        inner = f"{masthead}{tapes_el}{title_el}{deck}"
    return f'<section class="cover">{inner}{foot}</section>'


def _contents(book: Book) -> str:
    rows = []
    for i, ch in enumerate(book.chapters):
        secs = [b.text for b in ch.blocks if isinstance(b, Heading)]
        sec_html = (
            f'<div class="secs">{" &middot; ".join(_e(s) for s in secs)}</div>' if secs else ""
        )
        rows.append(
            f'<li><span class="n">{_e(ch.label)}</span><span class="t"><a href="#ch{i + 1}">'
            f"{_e(ch.title)}</a><small>{_e(ch.dek)}</small>{sec_html}</span>"
            f'<span class="p"><a href="#ch{i + 1}"></a></span></li>'
        )
    return (
        '<section class="contents"><h2>Contents</h2><ol class="toc">'
        + "".join(rows)
        + '</ol><div class="made"><b>How this book was made.</b> Pods transcribed the episode by '
        "voice, so every line knows who said it and when. The narrative is written fresh; words in "
        "quotation marks are the speakers' own, checked word for word against the recording and "
        "footnoted with their timestamp.</div></section>"
    )


def _closing(book: Book, notes: _Notes) -> str:
    big = ""
    if book.closing:
        notes.add(book.closing)
        big = (
            f'<blockquote class="big"><p>&#8220;{_e(book.closing.text)}&#8221;</p>'
            f"{_cite(book.closing)}</blockquote>"
        )
    rows = "".join(
        f'<tr><td class="ts">{_ts(q.start)}</td><td class="sp">{_e(q.speaker)}</td>'
        f"<td>&#8220;{_e(q.text)}&#8221;</td></tr>"
        for q in sorted(notes.quotes.values(), key=lambda q: q.start)
    )
    demo = " The episode and its speakers are fictional demo content." if book.demo else ""
    return (
        f'<section class="closing">{big}<div class="sources">'
        f"<h3>Every quote, and where it was said</h3><table>{rows}</table></div>"
        f'<p class="colophon">Made with Pods from {_e(book.podcast_title)}, episode '
        f"{book.episode_number}: {_e(book.episode_title)}.{demo}</p></section>"
    )


def render_html(
    book: Book, segments: Sequence[Segment], theme: Theme, cover_image_uri: str | None = None
) -> str:
    notes = _Notes()
    chapters = "".join(
        _chapter(ch, i, book, segments, theme, notes) for i, ch in enumerate(book.chapters)
    )
    cover = _cover(book, segments, theme, cover_image_uri)
    contents = _contents(book)
    closing = _closing(book, notes)
    classes = " ".join(
        [
            f"cover-{theme.cover_layout}",
            f"art-{theme.art}",
            f"opener-{theme.opener_style}",
            f"pull-{theme.pull_style}",
            "caps" if theme.heading_caps else "nocaps",
        ]
    )
    return (
        f'<!doctype html><html lang="en" class="{classes}"><head><meta charset="utf-8">'
        f"<title>{_e(book.title)}</title><style>{_theme_css(theme)}\n{CSS_PATH.read_text()}</style>"
        f'</head><body><span class="book-title-string">{_e(book.title.upper())}</span>'
        f"{cover}{contents}{chapters}{closing}</body></html>"
    )


def render_pdf(
    book: Book,
    segments: Sequence[Segment],
    theme: Theme,
    out_path: Path,
    artwork: Path | None = None,
) -> Path:
    """Render the book. `artwork` (the podcast's image) is used when the theme's art is "image"."""
    from weasyprint import HTML  # imported lazily: heavy, and only needed when rendering

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image_uri = None
    if theme.art == "image" and artwork and artwork.is_file():
        w, h = COVER_ART_SIZE[theme.cover_layout]
        px = (round(w / 25.4 * 220), round(h / 25.4 * 220))  # 220 dpi
        art = duotone(
            artwork,
            out_path.with_name(f"{out_path.stem}-cover.png"),
            theme.palette.primary,
            theme.palette.tint,
            px,
        )
        image_uri = art.as_uri()
    html = render_html(book, segments, theme, image_uri)
    HTML(string=html, base_url=str(out_path.parent)).write_pdf(out_path)
    return out_path
