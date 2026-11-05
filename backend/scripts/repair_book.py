"""Re-check and re-render an existing book with the current verifier (no model calls).

    DATA_DIR=../data uv run python -m scripts.repair_book <book_id>
"""

import sys

from app.books.pipeline import repair_book


def main() -> None:
    row = repair_book(int(sys.argv[1]))
    print(f"book {row.id}: {row.pages} pages, {row.words} words, {row.quotes} quotes")


if __name__ == "__main__":
    main()
