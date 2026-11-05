import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  isJobActive,
  useCancelJob,
  useClearFinishedJobs,
  useDeleteJob,
  useConfig,
  useEpisodes,
  useJobs,
  useRebuildIndex,
  useRetryJob,
} from '../api/hooks'
import type { Job, JobKind, JobStatus } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { IconClose, IconRefresh, IconTrash } from '../components/Icons'
import { Skeleton, Spinner } from '../components/Spinner'
import { StatusStamp } from '../components/StatusStamp'
import { useToast } from '../components/ToastContext'
import {
  fmtElapsed,
  fmtEpNumber,
  fmtNumber,
  fmtRelativeDate,
} from '../utils/format'
import './JobsPage.css'

type JobViewFilter = 'all' | 'active' | JobStatus

function formatKind(kind: JobKind): string {
  switch (kind) {
    case 'process':
      return 'Process'
    case 'summarize':
      return 'Summarize'
    case 'reindex':
      return 'Re-index'
    case 'rebuild_index':
      return 'Rebuild index'
    case 'book':
      return 'Book'
  }
}

function fmtClockTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function JobsPage() {
  const { pushToast } = useToast()
  const { data: config } = useConfig()
  const {
    data: jobs,
    isLoading,
    error,
    refetch,
  } = useJobs({ limit: 200 })
  const { data: episodesCatalog } = useEpisodes({ limit: 500 })

  const cancelJob = useCancelJob()
  const retryJob = useRetryJob()
  const deleteJob = useDeleteJob()
  const clearFinished = useClearFinishedJobs()
  const [confirmClear, setConfirmClear] = useState(false)
  const rebuildIndex = useRebuildIndex()

  const [viewFilter, setViewFilter] = useState<JobViewFilter>('all')
  const [busyJobId, setBusyJobId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmRebuild, setConfirmRebuild] = useState(false)

  const epNumberById = useMemo(() => {
    const map = new Map<number, number>()
    if (!episodesCatalog) return map
    for (const ep of episodesCatalog.items) {
      map.set(ep.id, ep.number)
    }
    return map
  }, [episodesCatalog])

  const counts = useMemo(() => {
    const all = jobs ?? []
    return {
      all: all.length,
      active: all.filter(isJobActive).length,
      done: all.filter((j) => j.status === 'done').length,
      failed: all.filter((j) => j.status === 'failed').length,
      cancelled: all.filter((j) => j.status === 'cancelled').length,
    }
  }, [jobs])

  const visibleJobs = useMemo<Job[]>(() => {
    const all = jobs ?? []
    if (viewFilter === 'all') return all
    if (viewFilter === 'active') return all.filter(isJobActive)
    return all.filter((j) => j.status === viewFilter)
  }, [jobs, viewFilter])

  const handleCancel = (jobId: number) => {
    setActionError(null)
    setBusyJobId(jobId)
    cancelJob.mutate(jobId, {
      onSettled: () => setBusyJobId(null),
      onError: (err) => {
        setActionError(err instanceof ApiError ? err.detail : 'Could not cancel job.')
      },
    })
  }

  const handleRetry = (jobId: number) => {
    setActionError(null)
    setBusyJobId(jobId)
    retryJob.mutate(jobId, {
      onSuccess: () => {
        pushToast({ message: 'Queued retry job.' })
      },
      onSettled: () => setBusyJobId(null),
      onError: (err) => {
        setActionError(err instanceof ApiError ? err.detail : 'Could not retry job.')
      },
    })
  }

  const handleDelete = (jobId: number) => {
    setActionError(null)
    setBusyJobId(jobId)
    deleteJob.mutate(jobId, {
      onSettled: () => setBusyJobId(null),
      onError: (err) => {
        setActionError(err instanceof ApiError ? err.detail : 'Could not delete job.')
      },
    })
  }

  const finishedCount = (jobs ?? []).filter(
    (j) => j.status === 'done' || j.status === 'failed' || j.status === 'cancelled',
  ).length

  const handleClearFinished = () => {
    setActionError(null)
    clearFinished.mutate(undefined, {
      onSuccess: ({ deleted }) => {
        setConfirmClear(false)
        pushToast({ message: `Cleared ${fmtNumber(deleted)} finished ${deleted === 1 ? 'job' : 'jobs'}.` })
      },
      onError: (err) => {
        setConfirmClear(false)
        setActionError(err instanceof ApiError ? err.detail : 'Could not clear finished jobs.')
      },
    })
  }

  const handleRebuildIndex = () => {
    setActionError(null)
    rebuildIndex.mutate(undefined, {
      onSuccess: () => {
        setConfirmRebuild(false)
        pushToast({ message: 'Queued full index rebuild job.' })
      },
      onError: (err) => {
        setActionError(err instanceof ApiError ? err.detail : 'Could not start index rebuild.')
      },
    })
  }

  const missingOpenAiKey = Boolean(config && !config.fake_mode && !config.has_openai_key)

  return (
    <main id="main-content" className="page-container jobs-page">
      <div className="page-header">
        <div className="jobs-title-group">
          <h1 className="page-title">Jobs</h1>
          {counts.active > 0 ? (
            <span className="jobs-live-note">
              Updating every 2s · {fmtNumber(counts.active)} active
            </span>
          ) : (
            <span className="jobs-live-note">Idle</span>
          )}
        </div>

        <div className="jobs-head-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled={finishedCount === 0 || clearFinished.isPending}
          onClick={() => setConfirmClear(true)}
          title={finishedCount === 0 ? 'No finished jobs to clear' : undefined}
        >
          <IconTrash size={13} />
          <span>Clear finished{finishedCount > 0 ? ` (${fmtNumber(finishedCount)})` : ''}</span>
        </button>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            if (config?.fake_mode) {
              handleRebuildIndex()
            } else {
              setConfirmRebuild((prev) => !prev)
            }
          }}
          disabled={rebuildIndex.isPending}
        >
          {rebuildIndex.isPending ? <Spinner size={12} label="Queueing" /> : <IconRefresh size={13} />}
          <span>Rebuild index</span>
        </button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmClear}
        title="Clear finished jobs?"
        description={`Removes ${fmtNumber(finishedCount)} done, failed and cancelled job ${finishedCount === 1 ? 'record' : 'records'} from this list. Episodes, transcripts and the index are not touched.`}
        confirmLabel="Clear finished"
        danger
        busy={clearFinished.isPending}
        onConfirm={handleClearFinished}
        onClose={() => setConfirmClear(false)}
      />

      {confirmRebuild ? (
        <div className="jobs-rebuild-confirm" role="region" aria-label="Confirm index rebuild">
          <div className="jobs-rebuild-body">
            <strong>Confirm full vector index rebuild</strong>
            {missingOpenAiKey ? (
              <p className="jobs-rebuild-warn">
                OPENAI_API_KEY is not configured on the server for embeddings.
              </p>
            ) : (
              <p>
                Re-embeds every transcribed episode on disk using{' '}
                <strong>{config?.embedding_model ?? 'embeddings'}</strong> ($
                {config?.prices.embedding_per_mtok ?? 0.02} / 1M tokens). Existing transcripts and
                audio are reused without re-downloading.
              </p>
            )}
          </div>
          <div className="jobs-rebuild-btns">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setConfirmRebuild(false)}
              disabled={rebuildIndex.isPending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={missingOpenAiKey || rebuildIndex.isPending}
              onClick={handleRebuildIndex}
            >
              Start rebuild
            </button>
          </div>
        </div>
      ) : null}

      {/* Filter bar — failed & cancelled always accessible and visible in "All" */}
      <div className="jobs-filter-bar" role="tablist" aria-label="Filter jobs by status">
        {(
          [
            { key: 'all', label: `All (${fmtNumber(counts.all)})` },
            { key: 'active', label: `Active (${fmtNumber(counts.active)})` },
            { key: 'done', label: `Done (${fmtNumber(counts.done)})` },
            { key: 'failed', label: `Failed (${fmtNumber(counts.failed)})` },
            { key: 'cancelled', label: `Cancelled (${fmtNumber(counts.cancelled)})` },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={viewFilter === tab.key}
            className={`jobs-filter-tab ${viewFilter === tab.key ? 'jobs-filter-tab--on' : ''}`.trim()}
            onClick={() => setViewFilter(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {actionError ? (
        <ErrorBanner
          message="Job action failed."
          recovery={actionError}
          onDismiss={() => setActionError(null)}
        />
      ) : null}

      {error ? (
        <ErrorBanner
          message="Could not load jobs queue."
          recovery={error instanceof ApiError ? error.detail : undefined}
          onRetry={() => void refetch()}
        />
      ) : isLoading && !jobs ? (
        <div className="jobs-skeletons">
          <Skeleton height="44px" />
          <Skeleton height="44px" />
          <Skeleton height="44px" />
        </div>
      ) : !jobs || jobs.length === 0 ? (
        <section className="jobs-pipeline" aria-labelledby="jobs-pipeline-heading">
          <h2 id="jobs-pipeline-heading" className="jobs-pipeline-heading">
            No background jobs yet
          </h2>
          <p className="jobs-pipeline-sub">
            When you process episodes in the Library, each one runs through three steps here. A
            finished step is never repeated, and everything is saved locally.
          </p>
          <ol className="jobs-pipeline-steps">
            <li className="jobs-pipeline-step">
              <StatusStamp status="downloaded" />
              <h3 className="jobs-pipeline-step-title">Download</h3>
              <p className="jobs-pipeline-step-text">
                The episode audio is fetched from its RSS feed and saved to your data folder.
                Free.
              </p>
            </li>
            <li className="jobs-pipeline-step">
              <StatusStamp status="transcribed" />
              <h3 className="jobs-pipeline-step-title">Transcribe</h3>
              <p className="jobs-pipeline-step-text">
                Audio is split into chunks and transcribed with speaker labels and timestamps
                {config ? ` using ${config.transcription_model}` : ''}. This is the paid step.
              </p>
            </li>
            <li className="jobs-pipeline-step">
              <StatusStamp status="indexed" />
              <h3 className="jobs-pipeline-step-title">Index</h3>
              <p className="jobs-pipeline-step-text">
                Speaker-aware passages are embedded
                {config ? ` with ${config.embedding_model}` : ''} into the local vector index,
                ready for Chat.
              </p>
            </li>
          </ol>
          <Link to="/library" className="btn btn-primary jobs-pipeline-cta">
            Choose episodes in the Library
          </Link>
        </section>
      ) : visibleJobs.length === 0 ? (
        <EmptyState
          title="No jobs match this filter"
          description="Switch back to All to inspect every historical, failed, or cancelled job."
          action={
            <button type="button" className="btn" onClick={() => setViewFilter('all')}>
              Show all jobs
            </button>
          }
        />
      ) : (
        <div className="table-wrap">
          <table className="data-table jobs-table">
            <thead>
              <tr>
                <th>Episode</th>
                <th className="jobs-col-kind">Kind &amp; steps</th>
                <th className="jobs-col-status">Status</th>
                <th className="jobs-col-progress">Progress &amp; details</th>
                <th className="jobs-col-timings">Timings</th>
                <th className="jobs-col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleJobs.map((job) => {
                const epNum =
                  job.episode_id !== null ? epNumberById.get(job.episode_id) : undefined
                const pct = Math.round(Math.max(0, Math.min(1, job.progress)) * 100)
                const canCancel = job.status === 'queued' || job.status === 'running'
                const canRetry = job.status === 'failed' || job.status === 'cancelled'
                const isRowBusy = busyJobId === job.id

                return (
                  <tr key={job.id}>
                    <td className="jobs-col-ep">
                      {job.episode_id !== null ? (
                        <Link to={`/episodes/${job.episode_id}`} className="jobs-ep-link">
                          {epNum !== undefined ? (
                            <span className="jobs-ep-num">{fmtEpNumber(epNum)} </span>
                          ) : null}
                          {job.episode_title ?? `Episode #${job.episode_id}`}
                        </Link>
                      ) : (
                        <span className="jobs-global-target">Full vector index</span>
                      )}
                    </td>

                    <td className="jobs-col-kind">
                      <span className="jobs-kind-name">{formatKind(job.kind)}</span>
                      {job.steps.length > 0 ? (
                        <span className="jobs-steps-trail">{job.steps.join(' · ')}</span>
                      ) : null}
                    </td>

                    <td className="jobs-col-status">
                      <StatusStamp
                        status={job.status}
                        progress={job.status === 'running' ? job.progress : undefined}
                      />
                    </td>

                    <td className="jobs-col-progress">
                      <div className="jobs-progress-cell">
                        {job.status === 'running' || job.status === 'done' ? (
                          <div className="jobs-bar-row">
                            <div className="jobs-bar-track" aria-hidden="true">
                              <div
                                className={`jobs-bar-fill ${job.status === 'done' ? 'jobs-bar-fill--done' : ''}`.trim()}
                                style={{
                                  width: `${job.status === 'done' ? 100 : pct}%`,
                                }}
                              />
                            </div>
                            {job.current_step ? (
                              <span className="jobs-step-label">{job.current_step}</span>
                            ) : null}
                          </div>
                        ) : null}

                        {job.message ? (
                          <span className="jobs-msg">{job.message}</span>
                        ) : null}

                        {job.error ? (
                          <p className="jobs-error-text" role="alert">
                            {job.error}
                          </p>
                        ) : null}
                      </div>
                    </td>

                    <td className="jobs-col-timings">
                      <span className="jobs-timing-primary">
                        {fmtRelativeDate(job.created_at)} {fmtClockTime(job.created_at)}
                      </span>
                      <span className="jobs-timing-elapsed">
                        {job.started_at
                          ? `Elapsed ${fmtElapsed(job.started_at, job.finished_at)}`
                          : 'Waiting'}
                      </span>
                    </td>

                    <td className="jobs-col-actions">
                      {canCancel ? (
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={isRowBusy}
                          onClick={() => handleCancel(job.id)}
                        >
                          {isRowBusy ? <Spinner size={12} label="Cancelling" /> : <IconClose size={12} />}
                          <span>Cancel</span>
                        </button>
                      ) : null}
                      {canRetry ? (
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={isRowBusy}
                          onClick={() => handleRetry(job.id)}
                        >
                          {isRowBusy ? <Spinner size={12} label="Retrying" /> : <IconRefresh size={12} />}
                          <span>Retry</span>
                        </button>
                      ) : null}
                      {!isJobActive(job) ? (
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          disabled={isRowBusy}
                          onClick={() => handleDelete(job.id)}
                          aria-label={`Delete job ${job.id} from history`}
                        >
                          <IconTrash size={12} />
                        </button>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
