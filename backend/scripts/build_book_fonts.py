"""Instance the variable book fonts into static per-weight files for WeasyPrint.

uv run python -m scripts.build_book_fonts
"""

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from app.books.theme import FONT_DIR, FONT_PAIRS, STATIC_DIR


def main() -> None:
    STATIC_DIR.mkdir(exist_ok=True)
    jobs = []
    for p in FONT_PAIRS:
        jobs += [(p.serif, w) for w in (400, 600, 700)]
        jobs += [(p.serif_italic, w) for w in (400, 600)]
        jobs += [(p.sans, w) for w in (400, 600, 700)]
    for stem, wght in jobs:
        font = TTFont(FONT_DIR / f"{stem}.ttf")
        axes = {a.axisTag: a for a in font["fvar"].axes}
        loc = {"wght": max(axes["wght"].minValue, min(axes["wght"].maxValue, wght))}
        if "opsz" in axes:  # text optical size; display sizes still read well
            loc["opsz"] = max(axes["opsz"].minValue, min(axes["opsz"].maxValue, 14))
        inst = instancer.instantiateVariableFont(font, loc, updateFontNames=False)
        out = STATIC_DIR / f"{stem}-{wght}.ttf"
        inst.save(out)
        print(out.name, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
