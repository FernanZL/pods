import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useCreateBook, useEstimateBook } from '../api/hooks'
import type { BookEstimate, BookForm, BookTense } from '../api/types'
import { fmtNumber, fmtUsd } from '../utils/format'
import { ConfirmDialog } from './ConfirmDialog'
import { IconBook } from './Icons'
import { Spinner } from './Spinner'
import { useToast } from './ToastContext'
import './MakeBookButton.css'

interface MakeBookButtonProps {
  episodeId: number
  disabledReason?: string
}

const NARRATOR = '' // radio value for the third-person narrator

/** How the book reads: the speaker's own book, or a retelling of the conversation. */
type Telling = 'book' | 'past' | 'present'

const RETELLINGS: { value: Telling; name: string; desc: string }[] = [
  { value: 'past', name: 'Retelling, looking back', desc: 'The conversation, told after it.' },
  { value: 'present', name: 'Retelling, as it happens', desc: 'The conversation, told live.' },
]

function asRequest(telling: Telling): { form: BookForm; tense: BookTense } {
  return {
    form: telling === 'book' ? 'book' : 'retelling',
    tense: telling === 'present' ? 'present' : 'past',
  }
}

/** "Andrew Huberman" -> "Andrew"; "Dr. K (Alok Kanojia)" -> "Dr. K". */
function shortName(name: string): string {
  const words = name.replace(/\s*\(.*?\)/g, '').trim().split(/\s+/)
  return words[0]?.endsWith('.') && words.length > 1 ? `${words[0]} ${words[1]}` : words[0] ?? name
}

/** Estimate, pick who tells it, confirm the cost, then start writing a long-form book. */
export function MakeBookButton({ episodeId, disabledReason }: MakeBookButtonProps) {
  const navigate = useNavigate()
  const { pushToast } = useToast()
  const estimate = useEstimateBook()
  const create = useCreateBook()
  const [est, setEst] = useState<BookEstimate | null>(null)
  const [voice, setVoice] = useState(NARRATOR)
  const [telling, setTelling] = useState<Telling>('book')
  const [error, setError] = useState<string | null>(null)

  const open = () => {
    setError(null)
    estimate.mutate(episodeId, {
      onSuccess: (data) => {
        // Default: the host's own book (the speaker listed first); else a narrated retelling.
        const first = data.voices[0]?.label ?? NARRATOR
        setVoice(first)
        setTelling(first ? 'book' : 'past')
        setEst(data)
      },
      onError: (e) => setError(e instanceof ApiError ? e.detail : 'Could not estimate the book.'),
    })
  }

  const confirm = () => {
    create.mutate(
      { episodeId, narrator: voice || null, ...asRequest(telling) },
      {
        onSuccess: () => {
          setEst(null)
          pushToast({ message: 'Writing your book. It appears in Books when it is ready.' })
          navigate('/books')
        },
        onError: (e) => {
          setEst(null)
          setError(e instanceof ApiError ? e.detail : 'Could not start the book.')
        },
      },
    )
  }

  const pickVoice = (next: string) => {
    if (!next && telling === 'book') setTelling('past')
    if (next && !voice) setTelling('book')
    setVoice(next)
  }
  const author = est?.voices.find((v) => v.label === voice)
  const tellings: { value: Telling; name: string; desc: string }[] = author
    ? [
        {
          value: 'book',
          name: `${shortName(author.name)}'s own book`,
          desc: `Written to you, like a book ${shortName(author.name)} wrote on the subject.`,
        },
        ...RETELLINGS,
      ]
    : RETELLINGS

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
      >
        {est && est.voices.length > 0 ? (
          <fieldset className="voice-picker" disabled={create.isPending}>
            <legend className="voice-legend">Who tells it</legend>
            <label className="voice-option">
              <input
                type="radio"
                name="book-voice"
                value={NARRATOR}
                checked={voice === NARRATOR}
                onChange={() => pickVoice(NARRATOR)}
              />
              <span className="voice-text">
                <span className="voice-name">A narrator</span>
                <span className="voice-desc">Third person, like a magazine feature.</span>
              </span>
            </label>
            {est.voices.map((v) => (
              <label className="voice-option" key={v.label}>
                <input
                  type="radio"
                  name="book-voice"
                  value={v.label}
                  checked={voice === v.label}
                  onChange={() => pickVoice(v.label)}
                />
                <span className="voice-text">
                  <span className="voice-name">
                    {v.name} <span className="voice-role">{v.role}</span>
                  </span>
                  <span className="voice-desc">First person, in {shortName(v.name)}'s voice.</span>
                </span>
              </label>
            ))}
            {author ? (
              <p className="voice-note">
                The PDF notes that the voice is written by AI from the episode, not by{' '}
                {author.name}.
              </p>
            ) : null}
          </fieldset>
        ) : null}
        {est ? (
          <fieldset className="voice-picker" disabled={create.isPending}>
            <legend className="voice-legend">How it reads</legend>
            <div className="tense-options">
              {tellings.map((t) => (
                <label className="voice-option" key={t.value}>
                  <input
                    type="radio"
                    name="book-telling"
                    value={t.value}
                    checked={telling === t.value}
                    onChange={() => setTelling(t.value)}
                  />
                  <span className="voice-text">
                    <span className="voice-name">{t.name}</span>
                    <span className="voice-desc">{t.desc}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}
      </ConfirmDialog>
    </>
  )
}
