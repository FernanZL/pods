import type { EpisodeStatus, JobStatus } from '../api/types'
import './StatusStamp.css'

export type StampVariant = EpisodeStatus | JobStatus | 'demo'

interface StatusStampProps {
  status: StampVariant
  progress?: number
  label?: string
}

function defaultLabel(status: StampVariant, progress?: number): string {
  switch (status) {
    case 'new':
      return 'New'
    case 'downloaded':
      return 'Downloaded'
    case 'transcribed':
      return 'Transcribed'
    case 'indexed':
      return 'Indexed'
    case 'queued':
      return 'Queued'
    case 'running': {
      if (progress !== undefined && Number.isFinite(progress)) {
        const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100)
        return `Running ${pct}%`
      }
      return 'Running'
    }
    case 'done':
      return 'Done'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    case 'demo':
      return 'Demo mode'
  }
}

function toneClass(status: StampVariant): string {
  switch (status) {
    case 'new':
    case 'queued':
      return 'status-stamp--new'
    case 'downloaded':
    case 'transcribed':
    case 'running':
      return 'status-stamp--progress'
    case 'indexed':
    case 'done':
      return 'status-stamp--done'
    case 'failed':
      return 'status-stamp--failed'
    case 'cancelled':
      return 'status-stamp--cancelled'
    case 'demo':
      return 'status-stamp--warn'
  }
}

/** Pipeline steps completed for an episode status (download → transcribe → index). */
const PIPELINE_STEPS: Partial<Record<StampVariant, number>> = {
  new: 0,
  downloaded: 1,
  transcribed: 2,
  indexed: 3,
}

/**
 * A stamped state mark. Episode states carry a three-step pipeline tally; a running job
 * fills with its progress; done is double-ruled; cancelled stays visible, struck through.
 */
export function StatusStamp({ status, progress, label }: StatusStampProps) {
  const text = label ?? defaultLabel(status, progress)
  const steps = PIPELINE_STEPS[status]
  const fill =
    status === 'running' && progress !== undefined && Number.isFinite(progress)
      ? Math.round(Math.max(0, Math.min(1, progress)) * 100)
      : null
  const a11y = steps !== undefined ? `${text}, ${steps} of 3 steps complete` : undefined

  return (
    <span
      className={`status-stamp ${toneClass(status)} status-stamp--is-${status}`}
      aria-label={a11y}
      title={a11y}
    >
      {fill !== null ? (
        <span className="status-stamp-fill" style={{ width: `${fill}%` }} aria-hidden="true" />
      ) : null}
      {steps !== undefined ? (
        <span className="status-stamp-steps" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <span key={i} className={i < steps ? 'status-stamp-step is-on' : 'status-stamp-step'} />
          ))}
        </span>
      ) : null}
      <span className="status-stamp-text">{text}</span>
    </span>
  )
}
