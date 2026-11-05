import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useCreateBook, useEstimateBook } from '../api/hooks'
import type { BookEstimate } from '../api/types'
import { fmtNumber, fmtUsd } from '../utils/format'
import { ConfirmDialog } from './ConfirmDialog'
import { IconBook } from './Icons'
import { Spinner } from './Spinner'
import { useToast } from './ToastContext'

interface MakeBookButtonProps {
  episodeId: number
  disabledReason?: string
}

/** Estimate, confirm the cost, then start writing a long-form book from the episode. */
export function MakeBookButton({ episodeId, disabledReason }: MakeBookButtonProps) {
  const navigate = useNavigate()
  const { pushToast } = useToast()
  const estimate = useEstimateBook()
  const create = useCreateBook()
  const [est, setEst] = useState<BookEstimate | null>(null)
  const [error, setError] = useState<string | null>(null)

  const open = () => {
    setError(null)
    estimate.mutate(episodeId, {
      onSuccess: setEst,
      onError: (e) => setError(e instanceof ApiError ? e.detail : 'Could not estimate the book.'),
    })
  }

  const confirm = () => {
    create.mutate(episodeId, {
      onSuccess: () => {
        setEst(null)
        pushToast({ message: 'Writing your book. It appears in Books when it is ready.' })
        navigate('/books')
      },
      onError: (e) => {
        setEst(null)
        setError(e instanceof ApiError ? e.detail : 'Could not start the book.')
      },
    })
  }

  const cost = est
    ? est.llm_usd > 0
      ? `Writing uses ${est.model}, estimated ${fmtUsd(est.llm_usd)}.`
      : 'Demo mode: no model calls, no cost.'
    : ''

  return (
    <>
      <button
        type="button"
        className="btn btn-sm"
        disabled={Boolean(disabledReason) || estimate.isPending}
        title={disabledReason}
        onClick={open}
      >
        {estimate.isPending ? <Spinner size={12} label="Estimating" /> : <IconBook size={13} />}
        <span>Make a book</span>
      </button>
      {error ? (
        <span className="make-book-error" role="alert">
          {error}
        </span>
      ) : null}
      <ConfirmDialog
        open={est !== null}
        title="Make a book from this episode?"
        description={
          est
            ? `About ${fmtNumber(est.chapters)} chapters and ${fmtNumber(est.target_words)} words ` +
              `(around ${fmtNumber(est.est_pages)} pages), written from the full ` +
              `${fmtNumber(est.transcript_words)}-word transcript with every quote checked. ${cost} ` +
              'You can reshuffle the design for free afterwards.'
            : ''
        }
        confirmLabel="Write the book"
        danger={false}
        busy={create.isPending}
        onConfirm={confirm}
        onClose={() => setEst(null)}
      />
    </>
  )
}
