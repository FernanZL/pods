import { ApiError } from '../api/client'
import { useCheckEpisode } from '../api/hooks'
import type { TranscriptCheck } from '../api/types'
import { fmtRelativeDate, fmtTime } from '../utils/format'
import { IconRefresh } from './Icons'
import { Spinner } from './Spinner'
import { StatusStamp } from './StatusStamp'
import './TranscriptCheckPanel.css'

interface TranscriptCheckPanelProps {
  episodeId: number
  check: TranscriptCheck | null
  onSeek: (seconds: number) => void
}

/** Result of the automatic transcript check: gaps, loops, speaker shares and names. */
export function TranscriptCheckPanel({ episodeId, check, onSeek }: TranscriptCheckPanelProps) {
  const recheck = useCheckEpisode()
  const issues = check?.issues ?? []

  return (
    <section className="tcheck" aria-labelledby="tcheck-heading">
      <div className="tcheck-head">
        <h3 id="tcheck-heading" className="tcheck-title">
          Transcript check
        </h3>
        {check ? (
          <StatusStamp
            status={check.ok ? 'done' : 'failed'}
            label={check.ok ? 'Looks right' : 'Needs a look'}
          />
        ) : (
          <span className="tcheck-meta">Not checked yet</span>
        )}
        {check ? (
          <span className="tcheck-meta">
            {check.names_checked ? 'Speaker names verified · ' : ''}
            {fmtRelativeDate(check.checked_at)}
          </span>
        ) : null}
        <button
          type="button"
          className="btn btn-sm btn-ghost tcheck-run"
          disabled={recheck.isPending}
          onClick={() => recheck.mutate(episodeId)}
          title="Checks gaps, repeated text and speakers, and asks the model to confirm the speaker names (a fraction of a cent)."
        >
          {recheck.isPending ? <Spinner size={12} label="Checking" /> : <IconRefresh size={12} />}
          <span>{check ? 'Re-check' : 'Check now'}</span>
        </button>
      </div>

      {recheck.error ? (
        <p className="tcheck-error">
          {recheck.error instanceof ApiError ? recheck.error.detail : 'The check failed.'}
        </p>
      ) : null}

      {issues.length > 0 ? (
        <ul className="tcheck-list">
          {issues.map((i, k) => (
            <li key={k} className={`tcheck-item tcheck-item--${i.severity}`}>
              <span className="tcheck-sev">{i.severity}</span>
              <span className="tcheck-msg">{i.message}</span>
              {i.at !== null ? (
                <button type="button" className="tcheck-at" onClick={() => onSeek(i.at ?? 0)}>
                  {fmtTime(i.at)}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : check ? (
        <p className="tcheck-ok">
          No gaps, repeated text or speaker problems found.
        </p>
      ) : null}
    </section>
  )
}
