"""Long-form PDF books written from episodes."""

import json
import shutil
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app import storage
from app.books import pipeline
from app.books.theme import new_seed
from app.config import get_settings
from app.db import get_session
from app.jobs.worker import worker
from app.models import Book, Episode, Job, Podcast, utcnow
from app.schemas import BookCreate, BookEstimate, BookOut, BookQuote, BookVoice

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
_STATUSES = ("queued", "writing", "ready", "failed")


def _out(session: Session, book: Book) -> BookOut:
    assert book.id is not None
    episode = session.get(Episode, book.episode_id)
    podcast = session.get(Podcast, episode.podcast_id) if episode else None
    job = session.get(Job, book.job_id) if book.job_id else None
    status = book.status if book.status in _STATUSES else "failed"
    if job and job.status in ("queued", "running") and status != "ready":
        status = "queued" if job.status == "queued" else "writing"
    return BookOut(
        id=book.id,
        episode_id=book.episode_id,
        episode_number=episode.number if episode else 0,
        episode_title=episode.title if episode else "",
        podcast_title=podcast.title if podcast else "",
        status=status,  # validated against the BookOut literal
        job_id=book.job_id,
        progress=job.progress
        if job and status == "writing"
        else (1.0 if status == "ready" else 0.0),
        message=job.message if job and status in ("queued", "writing") else "",
        title=book.title or (episode.title if episode else ""),
        seed=book.seed,
        family=book.family,
        art=book.art,
        chapters=book.chapters,
        words=book.words,
        pages=book.pages,
        quotes=book.quotes,
        rejected_quotes=book.rejected_quotes,
        review_issues=book.review_issues or 0,
        review_fixed=book.review_fixed or 0,
        review_summary=book.review_summary or "",
        narrator=book.narrator or "",
        tense="present" if book.tense == "present" else "past",
        form="book" if book.form == "book" else "retelling",
        cost_usd=job.cost_usd if job else None,
        error=book.error,
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _get(session: Session, book_id: int) -> Book:
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def _transcribed_episode(session: Session, episode_id: int) -> Episode:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.transcript_path or not storage.to_abs(episode.transcript_path).is_file():
        raise HTTPException(status_code=409, detail="Transcribe this episode before making a book")
    return episode


def _voices(session: Session, episode: Episode) -> list[BookVoice]:
    assert episode.transcript_path
    transcript = storage.read_transcript(storage.to_abs(episode.transcript_path))
    podcast = session.get(Podcast, episode.podcast_id)
    roles = pipeline.speaker_roles(transcript, podcast.title if podcast else "")
    return [
        BookVoice(label=label, name=name, role=role)  # type: ignore[arg-type]
        for label, name, role in roles
        if not name.lower().startswith("speaker ")  # unnamed voices cannot narrate
    ]


@router.post("/books/estimate", response_model=BookEstimate)
def estimate(body: BookCreate, session: SessionDep) -> BookEstimate:
    episode = _transcribed_episode(session, body.episode_id)
    assert episode.transcript_path
    transcript = storage.read_transcript(storage.to_abs(episode.transcript_path))
    words, chapters, target, usd = pipeline.estimate_cost(transcript)
    settings = get_settings()
    return BookEstimate(
        episode_id=body.episode_id,
        transcript_words=words,
        chapters=chapters,
        target_words=target,
        est_pages=max(8, round(target / 330) + chapters + 4),
        llm_usd=0.0 if settings.llm_provider == "fake" else usd,
        model=settings.llm_model if settings.llm_provider != "fake" else "fake",
        voices=_voices(session, episode),
    )


@router.post("/books", response_model=BookOut, status_code=201)
def create_book(body: BookCreate, session: SessionDep) -> BookOut:
    episode = _transcribed_episode(session, body.episode_id)
    narrator = ""
    if body.narrator:
        # a speaker label, or a display name (a retry passes the failed book's narrator)
        voice = next(
            (v for v in _voices(session, episode) if body.narrator in (v.label, v.name)), None
        )
        if voice is None:
            raise HTTPException(status_code=422, detail="That speaker cannot narrate this book")
        narrator = voice.name
    if body.form == "book" and not narrator:
        raise HTTPException(status_code=422, detail="Pick the speaker whose book it is")
    job = Job(kind="book", episode_id=episode.id, status="queued", message="Queued")
    session.add(job)
    session.commit()
    book = Book(
        episode_id=body.episode_id,
        job_id=job.id,
        seed=new_seed(),
        title=episode.title,
        narrator=narrator,
        tense=body.tense,
        form=body.form,
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    assert job.id is not None
    worker.enqueue(job.id)
    return _out(session, book)


@router.get("/books", response_model=list[BookOut])
def list_books(session: SessionDep) -> list[BookOut]:
    books = session.exec(select(Book).order_by(col(Book.created_at).desc())).all()
    return [_out(session, b) for b in books]


@router.get("/books/quote", response_model=BookQuote | None)
def book_quote(session: SessionDep) -> BookQuote | None:
    """One verified pull quote from the finished books, the same all day."""
    rows = session.exec(select(Book).where(Book.status == "ready").order_by(col(Book.id))).all()
    picks: list[BookQuote] = []
    for book in rows:
        if not book.dir_path or book.id is None:
            continue
        path = storage.to_abs(book.dir_path) / "book.json"
        episode = session.get(Episode, book.episode_id)
        if episode is None or episode.id is None or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for chapter in data.get("chapters") or []:
            for block in chapter.get("blocks") or []:
                q = block.get("quote") if block.get("t") == "pull" else None
                if q and 3 <= len(str(q.get("text", "")).split()) <= 16:
                    picks.append(
                        BookQuote(
                            text=q["text"],
                            speaker=q["speaker"],
                            start=float(q["start"]),
                            episode_id=episode.id,
                            episode_number=episode.number,
                            book_id=book.id,
                            book_title=book.title,
                        )
                    )
    if not picks:
        return None
    return picks[date.today().toordinal() % len(picks)]


@router.get("/books/{book_id}", response_model=BookOut)
def get_book(book_id: int, session: SessionDep) -> BookOut:
    return _out(session, _get(session, book_id))


@router.post("/books/{book_id}/reshuffle", response_model=BookOut)
async def reshuffle(book_id: int, session: SessionDep) -> BookOut:
    """New design (seed) for the same text. Free: no model calls."""
    book = _get(session, book_id)
    if book.status != "ready":
        raise HTTPException(status_code=409, detail="The book is not finished yet")
    previous = book.seed
    book.seed = new_seed()
    book.updated_at = utcnow()
    session.add(book)
    session.commit()
    try:
        await run_in_threadpool(pipeline.render_book, book_id)
    except Exception as exc:
        book = _get(session, book_id)
        book.seed = previous
        session.add(book)
        session.commit()
        raise HTTPException(
            status_code=500, detail=f"Could not render the new design: {exc}"
        ) from exc
    session.expire_all()
    return _out(session, _get(session, book_id))


def _file(book: Book, name: str):
    if not book.dir_path:
        raise HTTPException(status_code=404, detail="This book has no files yet")
    path = storage.to_abs(book.dir_path) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="This book has no files yet")
    return path


@router.get("/books/{book_id}/pdf")
def book_pdf(book_id: int, session: SessionDep, download: bool = False) -> FileResponse:
    book = _get(session, book_id)
    path = _file(book, "book.pdf")
    filename = f"{storage.slugify(book.title or 'book', 60)}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/books/{book_id}/cover.png")
def book_cover(book_id: int, session: SessionDep) -> FileResponse:
    path = _file(_get(session, book_id), "cover.png")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: int, session: SessionDep) -> Response:
    book = _get(session, book_id)
    job = session.get(Job, book.job_id) if book.job_id else None
    if job and job.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="Cancel the book's job before deleting it")
    if book.dir_path:
        shutil.rmtree(storage.to_abs(book.dir_path), ignore_errors=True)
    session.delete(book)
    session.commit()
    return Response(status_code=204)
