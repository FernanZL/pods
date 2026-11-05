import { useEffect, useRef } from 'react'
import type { AppConfig, CostEstimate } from '../api/types'
import { fmtNumber, fmtUsd } from '../utils/format'
import { ErrorBanner } from './ErrorBanner'
import { Skeleton, Spinner } from './Spinner'
import { StatusStamp } from './StatusStamp'
import './CostConfirmDialog.css'

interface CostConfirmDialogProps {
  open: boolean
  config: AppConfig | undefined
  estimate: CostEstimate | null
  estimating: boolean
  estimateError: string | null
  submitting: boolean
  submitError: string | null
  onRetryEstimate?: () => void
  onConfirm: () => void
  onClose: () => void
}

export function CostConfirmDialog({
  open,
  config,
  estimate,
  estimating,
  estimateError,
  submitting,
  submitError,
  onRetryEstimate,
  onConfirm,
  onClose,
}: CostConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  const missingOpenAiKey = Boolean(config && !config.fake_mode && !config.has_openai_key)
  const missingOpenRouterKey = Boolean(
    config &&
      !config.fake_mode &&
      config.llm_provider === 'openrouter' &&
      !config.has_openrouter_key,
  )
  const keyBlocked = missingOpenAiKey || missingOpenRouterKey

  const runnableCount = estimate
    ? Math.max(0, estimate.episode_count - estimate.skipped_already_done)
    : 0
  const nothingToDo = Boolean(estimate && runnableCount === 0)

  const confirmDisabled =
    estimating || submitting || Boolean(estimateError) || !estimate || keyBlocked || nothingToDo

  return (
    <dialog
      ref={dialogRef}
      className="cost-dialog"
      aria-labelledby="cost-dialog-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current && !submitting) {
          onClose()
        }
      }}
    >
      <div className="cost-dialog-inner">
        <div className="cost-dialog-head">
          <h2 id="cost-dialog-title" className="cost-dialog-title">
            Confirm processing cost
          </h2>
          {config?.fake_mode ? <StatusStamp status="demo" /> : null}
        </div>

        <p className="cost-dialog-lead">
          Selected episodes will be downloaded, transcribed with speaker diarization, and embedded
          into your local vector index. Already completed steps are never repeated.
        </p>

        {keyBlocked ? (
          <div className="cost-dialog-block" role="alert">
            <strong>API key required to process episodes.</strong>
            <p>
              {missingOpenAiKey
                ? 'OPENAI_API_KEY is not set on the server. Transcription and embeddings require an OpenAI API key.'
                : 'OPENROUTER_API_KEY is not set on the server for speaker attribution.'}{' '}
              Add the key to <code>.env</code> and restart the backend, or enable offline demo mode
              (<code>LLM_PROVIDER=fake TRANSCRIBER=fake EMBEDDINGS_PROVIDER=fake DOWNLOAD_MODE=fake</code>).
            </p>
          </div>
        ) : null}

        {estimateError ? (
          <ErrorBanner
            message="Could not calculate cost estimate."
            recovery={estimateError}
            onRetry={onRetryEstimate}
          />
        ) : null}

        {estimating ? (
          <div className="cost-dialog-skeletons" aria-label="Calculating estimate">
            <Skeleton height="18px" width="65%" />
            <Skeleton height="18px" width="85%" />
            <Skeleton height="18px" width="50%" />
            <Skeleton height="24px" width="100%" />
          </div>
        ) : null}

        {!estimating && estimate ? (
          <>
            <dl className="cost-grid">
              <div className="cost-row">
                <dt>Episodes selected</dt>
                <dd>{fmtNumber(estimate.episode_count)}</dd>
              </div>
              <div className="cost-row">
                <dt>Already indexed (skipped)</dt>
                <dd>{fmtNumber(estimate.skipped_already_done)}</dd>
              </div>
              <div className="cost-row">
                <dt>Episodes to process</dt>
                <dd>{fmtNumber(runnableCount)}</dd>
              </div>
              <div className="cost-row">
                <dt>Known audio duration</dt>
                <dd>{estimate.known_minutes.toFixed(1)} min</dd>
              </div>
              {estimate.unknown_duration_count > 0 ? (
                <div className="cost-row cost-row--warn">
                  <dt>Episodes without feed duration</dt>
                  <dd>{fmtNumber(estimate.unknown_duration_count)}</dd>
                </div>
              ) : null}
            </dl>

            {estimate.unknown_duration_count > 0 ? (
              <p className="cost-note">
                {fmtNumber(estimate.unknown_duration_count)}{' '}
                {estimate.unknown_duration_count === 1 ? 'episode omits' : 'episodes omit'} duration
                in the RSS feed; actual cost for {estimate.unknown_duration_count === 1 ? 'it' : 'them'}{' '}
                depends on the downloaded audio length.
              </p>
            ) : null}

            <dl className="cost-grid cost-grid--money">
              <div className="cost-row">
                <dt>Transcription</dt>
                <dd>{fmtUsd(estimate.transcription_usd)}</dd>
              </div>
              <div className="cost-row">
                <dt>Embeddings</dt>
                <dd>{fmtUsd(estimate.embedding_usd)}</dd>
              </div>
              <div className="cost-row">
                <dt>Speaker naming (LLM)</dt>
                <dd>{fmtUsd(estimate.llm_usd)}</dd>
              </div>
              <div className="cost-row cost-row--total">
                <dt>Estimated total</dt>
                <dd>
                  {config?.fake_mode
                    ? '$0.00 (Demo mode)'
                    : fmtUsd(estimate.total_usd)}
                </dd>
              </div>
            </dl>

            {config ? (
              <div className="cost-models">
                <span className="cost-models-item">
                  Transcription: <strong>{config.transcription_model}</strong>
                </span>
                <span className="cost-models-sep">·</span>
                <span className="cost-models-item">
                  Embeddings: <strong>{config.embedding_model}</strong>
                </span>
                <span className="cost-models-sep">·</span>
                <span className="cost-models-item">
                  LLM: <strong>{config.llm_model}</strong>
                </span>
              </div>
            ) : null}

            {nothingToDo ? (
              <p className="cost-note">
                Every episode in this selection is already indexed. No new work is needed.
              </p>
            ) : null}
          </>
        ) : null}

        {submitError ? (
          <ErrorBanner message="Failed to queue jobs." recovery={submitError} />
        ) : null}

        <div className="cost-dialog-footer">
          <button type="button" className="btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onConfirm}
            disabled={confirmDisabled}
          >
            {submitting ? <Spinner size={13} label="Queueing" /> : null}
            {runnableCount > 0
              ? `Process ${fmtNumber(runnableCount)} ${runnableCount === 1 ? 'episode' : 'episodes'}`
              : 'Process episodes'}
          </button>
        </div>
      </div>
    </dialog>
  )
}
