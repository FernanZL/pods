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


def test_every_family_and_art_kind_appears_and_renders() -> None:
    from app.books.theme import ART_KINDS, FAMILIES

    themes = [make_theme(s) for s in range(1, 400)]
    assert {t.family for t in themes} == {f.name for f in FAMILIES}
    assert {t.art for t in themes} == set(ART_KINDS)
    for kind in ART_KINDS:
        theme = next(t for t in themes if t.art == kind)
        html = render_html(_book(), TR.segments, theme)  # image falls back without artwork
        assert f"art-{kind}" in html


def test_artwork_is_duotoned_into_the_cover(tmp_path) -> None:
    from PIL import Image

    art = tmp_path / "art.png"
    Image.new("RGB", (300, 300), (120, 80, 40)).save(art)
    theme = next(make_theme(s) for s in range(1, 400) if make_theme(s).art == "image")
    out = render_pdf(_book(), TR.segments, theme, tmp_path / "b.pdf", artwork=art)
    assert (tmp_path / "b-cover.png").is_file()
    assert out.read_bytes()[:5] == b"%PDF-"


SEAM = Transcript(
    episode_id=2,
    model="m",
    speakers={"A": "Host", "B": "Guest"},
    segments=[
        Segment("A", 0, 5, "Why fence lines? Honestly, I don't"),
        Segment("B", 5, 6, "Mm."),
        Segment("A", 6, 20, "know. I just think they're beautiful and old and quiet."),
        Segment(
            "B",
            20,
            40,
            "You have to sit there and ponder each movement of your hand and the ink on the page.",
        ),
        Segment("B", 40, 60, "I wrote about the dark side of human nature in the past decade."),
    ],
)


def test_quotes_survive_segment_seams_and_small_slips() -> None:
    q = find_quote(SEAM, "I don't know. I just think they're beautiful")
    assert q.speaker == "Host"  # majority of the matched words
    slip = find_quote(SEAM, "sit there and ponder each movement of my hand and the ink")
    assert "your hand" in slip.text and slip.speaker == "Guest"  # snapped to the real words


def test_hidden_speech_is_quoted_but_echoes_are_not() -> None:
    from app.books.verify import recover_hidden

    runs = recover_hidden(
        SEAM, ["She described having to sit there and ponder each movement of my hand."]
    )
    quotes = [r for r in runs if not isinstance(r, str)]
    assert quotes and "your hand" in quotes[0].text
    echo = recover_hidden(SEAM, ["Greene knew the dark side of human nature in the boardroom."])
    assert all(isinstance(r, str) for r in echo)
