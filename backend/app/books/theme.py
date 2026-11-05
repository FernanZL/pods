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
# Cover art: data-driven drawings of the conversation, decorative geometry, a plain
# colour field, or the podcast's own artwork (duotoned into the palette).
ART_KINDS = ("tapes", "rings", "dots", "waveform", "mosaic", "stripes", "field", "image")
COVER_LAYOUTS = ("band", "panel", "column")
OPENER_STYLES = ("box", "rule")
OPENER_ART = ("echo", "echo", "none")  # repeat the cover motif in a strip, or nothing


@dataclass(frozen=True)
class Family:
    """A colour family: hue ranges for primary (dark), accent and a second accent."""

    name: str
    primary: tuple[float, float]
    accent: tuple[float, float]
    accent2: tuple[float, float]
    primary_sat: tuple[float, float] = (0.45, 0.62)
    accent_sat: tuple[float, float] = (0.6, 0.75)
    warm_paper: bool = False


FAMILIES: list[Family] = [
    Family("Indigo & magenta", (232, 272), (312, 348), (198, 228)),
    Family("Forest & ochre", (140, 168), (32, 46), (78, 100), (0.35, 0.5), (0.7, 0.85), True),
    Family("Ink & vermilion", (214, 228), (4, 14), (30, 42), (0.35, 0.5), (0.72, 0.85), True),
    Family("Teal & coral", (178, 192), (6, 18), (40, 52), (0.5, 0.65), (0.65, 0.8), True),
    Family("Plum & mustard", (282, 300), (40, 50), (330, 345), (0.35, 0.5), (0.75, 0.9), True),
    Family("Oxblood & rose", (348, 360), (336, 352), (20, 32), (0.5, 0.65), (0.45, 0.6), True),
    Family("Navy & tangerine", (212, 222), (22, 32), (190, 202), (0.55, 0.7), (0.8, 0.92)),
    Family("Charcoal & electric", (222, 232), (210, 222), (160, 176), (0.08, 0.16), (0.8, 0.92)),
]


@dataclass(frozen=True)
class Palette:
    ink: str  # body text
    ink_muted: str
    paper: str  # page background (near white)
    primary: str  # boxes, headings (white text on it >= 7:1)
    primary_ink: str  # text on primary
    primary_soft: str  # secondary text on primary
    accent: str  # rules, drop caps, small caps labels (>= 4.5:1 on paper)
    accent2: str  # second accent (speaker colour, small marks)
    accent_light: str  # accent that reads on the primary box
    tint: str  # light panels
    tint2: str  # light panels, cool
    line: str  # hairlines
    speakers: tuple[str, str, str, str]  # tape colours for speakers in order


@dataclass(frozen=True)
class Theme:
    seed: int
    family: str
    palette: Palette
    fonts: FontPair
    art: str  # cover art kind (ART_KINDS); "image" falls back when there is no artwork
    fallback_art: str  # used when art == "image" but the podcast has no artwork
    opener_art: str  # "echo" (cover motif strip) or "none"
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


def _shade_until(
    h: float, sat: float, light: float, against: str, ratio: float, step: float
) -> str:
    """Move lightness by `step` until the colour reaches `ratio` contrast against `against`."""
    for _ in range(60):
        c = _hsl(h, sat, light)
        if contrast(c, against) >= ratio:
            return c
        light = min(0.97, max(0.03, light + step))
    return c


def _palette(rng: random.Random, fam: Family) -> Palette:
    hp = rng.uniform(*fam.primary)
    ha = rng.uniform(*fam.accent)
    hb = rng.uniform(*fam.accent2)
    sp = rng.uniform(*fam.primary_sat)
    sa = rng.uniform(*fam.accent_sat)
    paper = _hsl(30 if fam.warm_paper else hp, 0.45 if fam.warm_paper else 0.4, 0.985)
    primary_ink = _hsl(hp, 0.4, 0.97)
    # Guard rails: lightness is pushed until every pairing is readable.
    primary = _shade_until(hp, sp, rng.uniform(0.18, 0.26), primary_ink, 7.0, -0.02)
    accent = _shade_until(ha, sa, rng.uniform(0.38, 0.46), paper, 4.5, -0.02)
    accent_light = _shade_until(ha, sa, 0.72, primary, 4.5, +0.02)
    accent2 = _hsl(hb, rng.uniform(0.55, 0.75), rng.uniform(0.48, 0.56))
    ink = _shade_until(hp, 0.3, 0.14, paper, 12.0, -0.02)
    return Palette(
        ink=ink,
        ink_muted=_shade_until(hp, 0.15, 0.42, paper, 5.0, -0.02),
        paper=paper,
        primary=primary,
        primary_ink=primary_ink,
        primary_soft=_hsl(hp, 0.3, 0.84),
        accent=accent,
        accent2=accent2,
        accent_light=accent_light,
        tint=_hsl(ha, 0.55, 0.95),
        tint2=_hsl(hp, 0.35, 0.95),
        line=_hsl(hp, 0.15, 0.82),
        speakers=(
            _hsl(hp, max(0.35, sp), 0.55),
            _hsl(ha, sa, 0.6),
            _hsl(hb, 0.6, 0.58),
            _hsl(hp + 25, 0.35, 0.72),
        ),
    )


def make_theme(seed: int) -> Theme:
    """Deterministic theme for a seed."""
    rng = random.Random(seed)
    fam = rng.choice(FAMILIES)
    art = rng.choice(ART_KINDS)
    return Theme(
        seed=seed,
        family=fam.name,
        palette=_palette(rng, fam),
        fonts=rng.choice(FONT_PAIRS),
        art=art,
        fallback_art=rng.choice([a for a in ART_KINDS if a not in ("image", "field")]),
        opener_art=rng.choice(OPENER_ART),
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
