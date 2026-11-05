"""Book theme generation, quote verification and rendering (no model calls)."""

import pytest

from app.books.document import Book, Chapter, Paragraph, PullQuote
from app.books.render import render_html, render_pdf
from app.books.theme import contrast, make_theme
from app.books.verify import QuoteNotFound, find_quote, resolve_runs
from app.domain import Segment, Transcript

TR = Transcript(
    episode_id=1,
    model="fake",
    speakers={"A": "Host", "B": "Guest"},
    segments=[
        Segment("A", 0.0, 10.0, "Why does morning light matter so much for sleep?"),
        Segment(
            "B", 10.0, 30.0, "Bright morning light sets the clock. It starts a timer for melatonin."
        ),
        Segment("B", 30.5, 40.0, "That timer runs for about sixteen hours."),
    ],
)


def test_theme_is_deterministic_and_always_readable() -> None:
    assert make_theme(42) == make_theme(42)
    assert make_theme(1) != make_theme(2)
    for seed in range(1, 300):
        p = make_theme(seed).palette
        assert contrast(p.primary, p.primary_ink) >= 7
        assert contrast(p.accent, p.paper) >= 4.5


def test_quote_attribution_comes_from_the_segment_text() -> None:
    q = find_quote(TR, "It starts a timer for melatonin")
    assert (q.speaker, q.start) == ("Guest", 10.0)
    # spans two consecutive segments of the same speaker, punctuation ignored
    assert find_quote(TR, "a timer for melatonin, that timer runs").speaker == "Guest"
    with pytest.raises(QuoteNotFound):
        find_quote(TR, "Morning light cures insomnia completely")


def test_unverifiable_marked_quotes_become_plain_narrative() -> None:
    runs, rejected = resolve_runs(
        TR, "As the guest says, ⟦Bright morning light sets the clock⟧ and ⟦light is magic forever⟧."
    )
    assert rejected == ["light is magic forever"]
    quotes = [r for r in runs if not isinstance(r, str)]
    assert len(quotes) == 1 and quotes[0].speaker == "Guest"
    assert "light is magic forever" in "".join(r for r in runs if isinstance(r, str))


def _book() -> Book:
    q = find_quote(TR, "Bright morning light sets the clock")
    runs, _ = resolve_runs(TR, "Light first. ⟦It starts a timer for melatonin⟧, the guest says.")
    return Book(
        title="Test Book",
        title_accent="Book",
        deck="Deck.",
        podcast_title="Pod",
        episode_number=3,
        episode_title="Ep",
        speakers=["Host", "Guest"],
        duration=40.0,
        chapters=[Chapter("Part one", "Light", "Dek.", 0, 40, q, [Paragraph(runs), PullQuote(q)])],
        closing=q,
        demo=True,
    )


@pytest.mark.parametrize("seed", [3, 4, 5, 11])
def test_render_html_contains_verified_quotes_and_citations(seed: int) -> None:
    html = render_html(_book(), TR.segments, make_theme(seed))
    assert "It starts a timer for melatonin" in html
    assert "Guest</b>, 0:10" in html  # footnote citation
    assert "Every quote, and where it was said" in html


def test_render_pdf_smoke(tmp_path) -> None:
    out = render_pdf(_book(), TR.segments, make_theme(7), tmp_path / "b.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"
