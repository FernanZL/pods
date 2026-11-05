"""Speaker tapes as SVG: a conversation drawn as turns at their exact durations.

Each row is an equal slice of the time window; each mark is one speaker turn,
coloured by speaker. Colours are written as literal hex because SVG attributes
cannot read CSS custom properties in WeasyPrint.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from app.domain import Segment


def tapes_svg(
    segments: Sequence[Segment],
    start: float,
    end: float,
    *,
    rows: int,
    width: float,
    height: float,
    colors: Sequence[str],
    style: str,
    seed: int = 0,
    opacity: float = 1.0,
) -> str:
    """Render speaker turns between start and end (seconds) into a width x height SVG."""
    rng = random.Random(seed)
    span = max(1e-6, (end - start) / rows)
    row_h = height / rows
    order: dict[str, int] = {}
    marks: list[str] = []

    for r in range(rows):
        lo, hi = start + r * span, start + (r + 1) * span
        shift = rng.uniform(0, 0.08) * width
        row_op = opacity * rng.uniform(0.62, 1.0)
        for seg in segments:
            if seg.end <= lo or seg.start >= hi:
                continue
            idx = order.setdefault(seg.speaker, len(order))
            color = colors[idx % len(colors)]
            a, b = max(seg.start, lo), min(seg.end, hi)
            x = (a - lo) / span * width * 0.92 + shift
            w = max(0.5, (b - a) / span * width * 0.92 - 0.7)
            marks.append(_mark(style, x, r * row_h, w, row_h, color, row_op))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'width="{width:.1f}mm" height="{height:.1f}mm" preserveAspectRatio="none">'
        f"{''.join(marks)}</svg>"
    )


def _mark(style: str, x: float, y: float, w: float, row_h: float, color: str, op: float) -> str:
    fill = f'fill="{color}" fill-opacity="{op:.2f}"'
    if style == "pills":
        h = row_h * 0.5
        return (
            f'<rect x="{x:.2f}" y="{y + (row_h - h) / 2:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="{h / 2:.2f}" {fill}/>'
        )
    if style == "ticks":
        # a thin baseline for the turn plus a tall tick where it starts
        base_h = row_h * 0.12
        tick_h = row_h * 0.62
        cy = y + row_h / 2
        return (
            f'<rect x="{x:.2f}" y="{cy - base_h / 2:.2f}" width="{w:.2f}" '
            f'height="{base_h:.2f}" {fill}/>'
            f'<rect x="{x:.2f}" y="{cy - tick_h / 2:.2f}" width="{min(0.9, w):.2f}" '
            f'height="{tick_h:.2f}" {fill}/>'
        )
    if style == "blocks":
        h = row_h * 0.78
        return (
            f'<rect x="{x:.2f}" y="{y + (row_h - h) / 2:.2f}" width="{w:.2f}" '
            f'height="{h:.2f}" {fill}/>'
        )
    # bars (default)
    h = row_h * 0.42
    return (
        f'<rect x="{x:.2f}" y="{y + (row_h - h) / 2:.2f}" width="{w:.2f}" height="{h:.2f}" '
        f'rx="0.6" {fill}/>'
    )
