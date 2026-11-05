import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, bookCoverUrl, bookPdfUrl } from '../api/client'
import { useBooks, useCreateBook, useDeleteBook, useReshuffleBook } from '../api/hooks'
import type { Book } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { IconDownload, IconShuffle, IconTrash } from '../components/Icons'
import { Skeleton, Spinner } from '../components/Spinner'
import { StatusStamp } from '../components/StatusStamp'
import { useToast } from '../components/ToastContext'
import { fmtEpNumber, fmtNumber, fmtRelativeDate } from '../utils/format'
import './BooksPage.css'

export function BooksPage() {
  const { data: books, isLoading, error, refetch } = useBooks()
  const [deleting, setDeleting] = useState<Book | null>(null)
  const del = useDeleteBook()

  return (
    <main id="main-content" className="page-container books-page">
      <div className="page-header">
        <h1 className="page-title">Books</h1>
        <span className="books-note">
          Long-form PDFs written from your episodes. Every quote is checked against the recording.
        </span>
      </div>

      {error ? (
        <ErrorBanner
          message="Could not load your books."
          recovery={error instanceof ApiError ? error.detail : undefined}
          onRetry={() => void refetch()}
        />
      ) : isLoading && !books ? (
        <div className="books-grid">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height="420px" />
          ))}
        </div>
      ) : !books || books.length === 0 ? (
        <EmptyState
          title="No books yet"
          description="Open any transcribed episode and choose Make a book. Pods plans chapters from the whole conversation, writes them as a long-form feature, checks every quote word for word, and typesets a PDF with its own design."
          action={
            <Link to="/library" className="btn btn-primary">
              Choose an episode
            </Link>
          }
        />
      ) : (
        <ul className="books-grid">
          {books.map((b) => (
            <BookCard key={b.id} book={b} onDelete={() => setDeleting(b)} />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this book?"
        description={`"${deleting?.title ?? ''}" and its PDF will be removed. The episode and its transcript stay.`}
        confirmLabel="Delete book"
        danger
        busy={del.isPending}
        onConfirm={() => {
          if (!deleting) return
          del.mutate(deleting.id, { onSettled: () => setDeleting(null) })
        }}
        onClose={() => setDeleting(null)}
      />
    </main>
  )
}

function BookCard({ book, onDelete }: { book: Book; onDelete: () => void }) {
  const reshuffle = useReshuffleBook()
  const retry = useCreateBook()
  const { pushToast } = useToast()
  const [err, setErr] = useState<string | null>(null)
  const working = book.status === 'queued' || book.status === 'writing'
  const ready = book.status === 'ready'

  const stats = [
    book.chapters ? `${fmtNumber(book.chapters)} chapters` : null,
    book.words ? `${fmtNumber(book.words)} words` : null,
    book.pages ? `${fmtNumber(book.pages)} pages` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <li className="book-card">
      <div className="book-cover-frame">
        {ready ? (
          <a href={bookPdfUrl(book.id)} target="_blank" rel="noreferrer" className="book-cover-link">
            <img
              className="book-cover"
              src={bookCoverUrl(book.id, `${book.seed}`)}
              alt={`Cover of ${book.title}`}
              loading="lazy"
            />
            {reshuffle.isPending ? (
              <span className="book-cover-busy">
                <Spinner size={18} label="Designing" />
              </span>
            ) : null}
          </a>
        ) : (
          <div className={`book-cover-placeholder ${book.status === 'failed' ? 'is-failed' : ''}`}>
            <span className="book-placeholder-title">{book.title}</span>
            {working ? (
              <div className="book-progress" aria-live="polite">
                <div className="book-progress-track">
                  <span
                    className="book-progress-fill"
                    style={{ width: `${Math.round(Math.max(0.03, book.progress) * 100)}%` }}
                  />
                </div>
                <span className="book-progress-msg">{book.message || 'Queued'}</span>
              </div>
            ) : (
              <span className="book-failed-msg">{book.error ?? 'Something went wrong.'}</span>
            )}
          </div>
        )}
      </div>

      <div className="book-body">
        <div className="book-title-row">
          <h2 className="book-title">{book.title}</h2>
          {!ready ? (
            <StatusStamp
              status={working ? 'running' : 'failed'}
              label={book.status === 'queued' ? 'Queued' : working ? 'Writing' : 'Failed'}
            />
          ) : null}
        </div>
        <Link to={`/episodes/${book.episode_id}`} className="book-episode">
          {fmtEpNumber(book.episode_number)} · {book.episode_title}
        </Link>
        <span className="book-meta">
          {book.podcast_title} · {fmtRelativeDate(book.created_at)}
        </span>
        {stats ? <span className="book-stats">{stats}</span> : null}
        {ready && book.review_summary ? (
          <span className="book-editor" title={book.review_summary}>
            {book.review_issues === 0
              ? 'Editor: no accuracy issues found'
              : `Editor: ${fmtNumber(book.review_issues)} ${book.review_issues === 1 ? 'issue' : 'issues'} found, ${fmtNumber(book.review_fixed)} fixed`}
          </span>
        ) : null}
        {ready ? (
          <span className="book-design">
            {book.family} · {book.art} cover · {fmtNumber(book.quotes)} verified quotes
          </span>
        ) : null}

        {err ? <p className="book-err">{err}</p> : null}

        <div className="book-actions">
          {ready ? (
            <>
              <a className="btn btn-sm btn-primary" href={bookPdfUrl(book.id)} target="_blank" rel="noreferrer">
                Open
              </a>
              <a className="btn btn-sm" href={bookPdfUrl(book.id, true)}>
                <IconDownload size={12} />
                <span>Download</span>
              </a>
              <button
                type="button"
                className="btn btn-sm"
                disabled={reshuffle.isPending}
                title="New colours, fonts and cover for the same text. Free."
                onClick={() => {
                  setErr(null)
                  reshuffle.mutate(book.id, {
                    onSuccess: (b) => pushToast({ message: `New design: ${b.family}, ${b.art} cover.` }),
                    onError: (e) =>
                      setErr(e instanceof ApiError ? e.detail : 'Could not reshuffle the design.'),
                  })
                }}
              >
                {reshuffle.isPending ? <Spinner size={12} label="Designing" /> : <IconShuffle size={12} />}
                <span>Reshuffle design</span>
              </button>
            </>
          ) : book.status === 'failed' ? (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={retry.isPending}
              onClick={() =>
                retry.mutate(book.episode_id, {
                  onError: (e) =>
                    setErr(e instanceof ApiError ? e.detail : 'Could not start a new book.'),
                })
              }
            >
              Try again
            </button>
          ) : (
            <Link to="/jobs" className="btn btn-sm">
              View job
            </Link>
          )}
          {!working ? (
            <button
              type="button"
              className="btn btn-sm btn-ghost book-delete"
              onClick={onDelete}
              aria-label={`Delete ${book.title}`}
            >
              <IconTrash size={12} />
            </button>
          ) : null}
        </div>
      </div>
    </li>
  )
}
