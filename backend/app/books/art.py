"""Cover and opener art. Most kinds are drawn from the conversation itself.

Every function returns markup for a width x height (mm) box:
- tapes     rows of speaker turns at exact durations (see tapes.py)
- rings     the conversation wound into concentric arcs
- dots      a dot matrix of moments; size = how much was said, colour = who said it
- waveform  mirrored bars like an audio wave, coloured by speaker
- mosaic    one tile per turn, flowing like text, width = duration
- stripes   bold diagonal bands of the palette (decorative)
- field     a plain colour field
- image     the podcast artwork, duotoned into the palette (prepared by `duotone`)

Colours are literal hex: SVG attributes cannot read CSS custom properties.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from pathlib import Path

from app.books.tapes import tapes_svg
from app.books.theme import Theme
from app.domain import Segment


def _svg(width: float, height: float, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'width="{width:.1f}mm" height="{height:.1f}mm" preserveAspectRatio="none">{body}</svg>'
    )


def _slices(segs: Sequence[Segment], start: float, end: float, n: int):
    """Split [start, end] into n slices -> (speaker index, words spoken) per slice."""
    order: dict[str, int] = {}
    for s in segs:
        order.setdefault(s.speaker, len(order))
    span = max(1e-6, (end - start) / n)
    out = []
    for i in range(n):
        lo, hi = start + i * span, start + (i + 1) * span
        by_spk: dict[str, float] = {}
        words = 0.0
        for s in segs:
            overlap = min(s.end, hi) - max(s.start, lo)
            if overlap <= 0:
                continue
            frac = overlap / max(1e-6, s.end - s.start)
            w = len(s.text.split()) * frac
            words += w
            by_spk[s.speaker] = by_spk.get(s.speaker, 0) + overlap
        spk = max(by_spk, key=by_spk.get) if by_spk else None
        out.append((order.get(spk, 0) if spk else -1, words))
    return out


def _rings(segs, start, end, w, h, colors, rng) -> str:
    cx = rng.choice((w * 0.5, w * 0.78, w * 0.22))
    cy = rng.choice((h * 0.5, h * 0.9, h * 0.15))
    rings = rng.randint(7, 11)
    max_r = math.hypot(max(cx, w - cx), max(cy, h - cy)) * rng.uniform(0.85, 1.05)
    gap = max_r / (rings + 1)
    span = (end - start) / rings
    order: dict[str, int] = {}
    paths = []
    for r in range(rings):
        radius = gap * (r + 1.2)
        lo, hi = start + r * span, start + (r + 1) * span
        rot = rng.uniform(0, 2 * math.pi)
        for s in segs:
            if s.end <= lo or s.start >= hi:
                continue
            idx = order.setdefault(s.speaker, len(order))
            a1 = rot + (max(s.start, lo) - lo) / span * 2 * math.pi * 0.96
            a2 = rot + (min(s.end, hi) - lo) / span * 2 * math.pi * 0.96 - 0.02
            if a2 <= a1:
                continue
            x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
            x2, y2 = cx + radius * math.cos(a2), cy + radius * math.sin(a2)
            large = 1 if a2 - a1 > math.pi else 0
            paths.append(
                f'<path d="M{x1:.2f} {y1:.2f} A{radius:.2f} {radius:.2f} 0 {large} 1 {x2:.2f} '
                f'{y2:.2f}" fill="none" stroke="{colors[idx % len(colors)]}" '
                f'stroke-width="{gap * 0.5:.2f}" stroke-linecap="butt"/>'
            )
    return _svg(w, h, "".join(paths))


def _dots(segs, start, end, w, h, colors, rng) -> str:
    cols = rng.choice((18, 22, 26))
    rows = max(3, round(cols * h / w))
    cell = min(w / cols, h / rows)
    data = _slices(segs, start, end, cols * rows)
    peak = max((d[1] for d in data), default=1) or 1
    out = []
    for i, (spk, words) in enumerate(data):
        r, c = divmod(i, cols)
        if spk < 0:
            continue
        rad = cell * (0.16 + 0.3 * math.sqrt(words / peak))
        cx = c * (w / cols) + w / cols / 2
        cy = r * (h / rows) + h / rows / 2
        out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rad:.2f}" fill="{colors[spk % 4]}"/>')
    return _svg(w, h, "".join(out))


def _waveform(segs, start, end, w, h, colors, rng) -> str:
    n = rng.choice((70, 90, 110))
    data = _slices(segs, start, end, n)
    peak = max((d[1] for d in data), default=1) or 1
    bw = w / n
    mid = h / 2
    out = []
    for i, (spk, words) in enumerate(data):
        if spk < 0:
            continue
        bh = max(0.8, (h * 0.92) * math.sqrt(words / peak) * rng.uniform(0.75, 1.0))
        out.append(
            f'<rect x="{i * bw + bw * 0.18:.2f}" y="{mid - bh / 2:.2f}" width="{bw * 0.64:.2f}" '
            f'height="{bh:.2f}" rx="{bw * 0.32:.2f}" fill="{colors[spk % 4]}"/>'
        )
    return _svg(w, h, "".join(out))


def _mosaic(segs, start, end, w, h, colors, rng) -> str:
    turns = [s for s in segs if s.end > start and s.start < end]
    if not turns:
        return _svg(w, h, "")
    rows = rng.choice((4, 5, 6, 7))
    total = sum(min(s.end, end) - max(s.start, start) for s in turns)
    per_row = total / rows
    row_h = h / rows
    gap = 1.2
    order: dict[str, int] = {}
    out = []
    x, r = 0.0, 0
    for s in turns:
        idx = order.setdefault(s.speaker, len(order))
        remaining = (min(s.end, end) - max(s.start, start)) / per_row * w
        while remaining > 0.01 and r < rows:
            piece = min(remaining, w - x)
            if piece > gap:
                out.append(
                    f'<rect x="{x:.2f}" y="{r * row_h:.2f}" width="{piece - gap:.2f}" '
                    f'height="{row_h - gap:.2f}" fill="{colors[idx % 4]}"/>'
                )
            x += piece
            remaining -= piece
            if x >= w - 0.01:
                x, r = 0.0, r + 1
    return _svg(w, h, "".join(out))


def _stripes(w, h, theme: Theme, rng) -> str:
    p = theme.palette
    pool = [p.primary, p.accent, p.accent2, p.tint, p.speakers[0], p.speakers[3]]
    angle = rng.choice((-30, -18, 18, 30, 45))
    out = []
    x = -h * 2
    while x < w + h * 2:
        band = rng.uniform(6, 26)
        out.append(
            f'<rect x="{x:.2f}" y="{-h:.2f}" width="{band:.2f}" height="{h * 3:.2f}" '
            f'fill="{rng.choice(pool)}"/>'
        )
        x += band + rng.choice((0, 0, 2.5, 6))
    body = f'<g transform="rotate({angle} {w / 2:.1f} {h / 2:.1f})">{"".join(out)}</g>'
    return _svg(
        w,
        h,
        f'<clipPath id="c"><rect width="{w}" height="{h}"/></clipPath>'
        f'<g clip-path="url(#c)">{body}</g>',
    )


def _field(w, h, theme: Theme, rng) -> str:
    p = theme.palette
    color = rng.choice((p.accent, p.accent2, p.speakers[0], p.primary))
    return _svg(w, h, f'<rect width="{w}" height="{h}" fill="{color}"/>')


def art_markup(
    kind: str,
    segs: Sequence[Segment],
    start: float,
    end: float,
    w: float,
    h: float,
    theme: Theme,
    *,
    salt: int = 0,
    rows: int | None = None,
    image_uri: str | None = None,
) -> str:
    """Markup for one art box. `salt` varies the drawing between chapters."""
    rng = random.Random(theme.seed * 31 + salt)
    colors = theme.palette.speakers
    if kind == "image":
        if image_uri:
            return (
                f'<img class="art-img" src="{image_uri}" alt="" style="width:{w}mm;height:{h}mm">'
            )
        kind = theme.fallback_art
    if kind == "rings":
        return _rings(segs, start, end, w, h, colors, rng)
    if kind == "dots":
        return _dots(segs, start, end, w, h, colors, rng)
    if kind == "waveform":
        return _waveform(segs, start, end, w, h, colors, rng)
    if kind == "mosaic":
        return _mosaic(segs, start, end, w, h, colors, rng)
    if kind == "stripes":
        return _stripes(w, h, theme, rng)
    if kind == "field":
        return _field(w, h, theme, rng)
    return tapes_svg(
        segs,
        start,
        end,
        rows=rows or theme.tape_rows,
        width=w,
        height=h,
        colors=colors,
        style=theme.tape_style,
        seed=theme.seed + salt,
    )


def duotone(src: Path, dst: Path, dark: str, light: str, size_px: tuple[int, int]) -> Path:
    """Crop `src` to the target aspect and map its tones from `dark` to `light`."""
    from PIL import Image, ImageOps

    img = Image.open(src).convert("L")
    img = ImageOps.fit(img, size_px, Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)
    out = ImageOps.colorize(img, black=dark, white=light)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "PNG", optimize=True)
    return dst
