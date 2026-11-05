"""Seeded book themes: every book gets its own look, always within the Pods family.

A theme is fully determined by an integer seed, so a book can be re-rendered
identically or "reshuffled" (new seed, same text) without any model calls.

Variation is bounded on purpose:
- colours jitter in hue around indigo (primary), magenta (accent) and sky blue
  (accent 2), with lightness fixed so contrast on white always holds;
- fonts come from a short list of curated serif + sans pairings;
- the speaker-tape motif, cover layout, chapter opener and small ornaments are
  each picked from a few variants.
"""

from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"
STATIC_DIR = FONT_DIR / "static"  # per-weight instances, see scripts/build_book_fonts.py


@dataclass(frozen=True)
class FontPair:
    name: str
    serif: str  # file stem, roman
    serif_italic: str
    sans: str
    display_weight: int  # weight used for big titles
    display_tracking: str  # letter-spacing for big titles


FONT_PAIRS: list[FontPair] = [
    FontPair("Source", "SourceSerif4", "SourceSerif4-Italic", "SourceSans3", 700, "-0.028em"),
    FontPair("Literata", "Literata", "Literata-Italic", "WorkSans", 700, "-0.025em"),
    FontPair("Bitter", "Bitter", "Bitter-Italic", "Figtree", 700, "-0.02em"),
    FontPair("Alegreya", "Alegreya", "Alegreya-Italic", "LibreFranklin", 700, "-0.015em"),
]

TAPE_STYLES = ("bars", "pills", "ticks", "blocks")
COVER_LAYOUTS = ("band", "panel", "column")
OPENER_STYLES = ("box", "rule")


@dataclass(frozen=True)
class Palette:
    ink: str  # body text
    ink_muted: str
    paper: str  # page background (near white)
    primary: str  # boxes, headings (white text on it >= 7:1)
    primary_ink: str  # text on primary
    primary_soft: str  # secondary text on primary
    accent: str  # rules, drop caps, small caps labels (>= 4.5:1 on paper)
    accent2: str  # cool second accent (speaker colour, small marks)
    tint: str  # light panels
    tint2: str  # light panels, cool
    line: str  # hairlines
    speakers: tuple[str, str, str, str]  # tape colours for speakers in order


@dataclass(frozen=True)
class Theme:
    seed: int
    palette: Palette
    fonts: FontPair
    tape_style: str
    tape_rows: int
    cover_layout: str
    opener_style: str
    dropcap: bool
    heading_caps: bool  # small uppercase section heads vs. sentence-case italic
    pull_style: str  # "rule" (accent rule above) or "bar" (tinted block)


def _hsl(h: float, s: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, light, s)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _luminance(hex_color: str) -> float:
    c = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _palette(rng: random.Random) -> Palette:
    hp = rng.uniform(232, 272)  # indigo, leaning blue or violet
    ha = rng.uniform(312, 348)  # magenta, leaning violet or rose
    hc = rng.uniform(198, 228)  # sky blue
    primary = _hsl(hp, rng.uniform(0.48, 0.62), rng.uniform(0.2, 0.26))
    accent = _hsl(ha, rng.uniform(0.58, 0.7), rng.uniform(0.38, 0.43))
    accent2 = _hsl(hc, rng.uniform(0.55, 0.7), rng.uniform(0.5, 0.56))
    paper = _hsl(hp, 0.4, 0.988)
    pal = Palette(
        ink=_hsl(hp, 0.35, 0.12),
        ink_muted=_hsl(hp, 0.18, 0.4),
        paper=paper,
        primary=primary,
        primary_ink=_hsl(hp, 0.6, 0.97),
        primary_soft=_hsl(hp, 0.45, 0.84),
        accent=accent,
        accent2=accent2,
        tint=_hsl(ha, 0.6, 0.95),
        tint2=_hsl(hp, 0.55, 0.955),
        line=_hsl(hp, 0.25, 0.82),
        speakers=(
            _hsl(hp + rng.uniform(-8, 8), 0.62, 0.62),
            _hsl(ha, 0.62, 0.66),
            _hsl(hc, 0.62, 0.62),
            _hsl(hp + 30, 0.5, 0.7),
        ),
    )
    # Guard rails: never ship unreadable combinations.
    assert contrast(pal.primary, pal.primary_ink) >= 7, "primary too light"
    assert contrast(pal.accent, pal.paper) >= 4.5, "accent too light"
    assert contrast(pal.ink, pal.paper) >= 12, "ink too light"
    return pal


def make_theme(seed: int) -> Theme:
    """Deterministic theme for a seed."""
    rng = random.Random(seed)
    return Theme(
        seed=seed,
        palette=_palette(rng),
        fonts=rng.choice(FONT_PAIRS),
        tape_style=rng.choice(TAPE_STYLES),
        tape_rows=rng.choice((6, 7, 8, 9)),
        cover_layout=rng.choice(COVER_LAYOUTS),
        opener_style=rng.choice(OPENER_STYLES),
        dropcap=rng.random() < 0.75,
        heading_caps=rng.random() < 0.6,
        pull_style=rng.choice(("rule", "bar")),
    )


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 2**31)
