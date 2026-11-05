import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, episodeAudioUrl } from '../api/client'
import {
  isJobActive,
  useConfig,
  useDeleteEpisodeData,
  useEpisode,
  useEpisodeCitations,
  useEstimateEpisodes,
  useJobs,
  useProcessEpisodes,
  useReindexEpisode,
  useSummarizeEpisode,
} from '../api/hooks'
import type {
  CostEstimate,
  EpisodeCitationRef,
  EpisodeDetail,
  EpisodeStatus,
  Segment,
} from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { CostConfirmDialog } from '../components/CostConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { MakeBookButton } from '../components/MakeBookButton'
import { ErrorBanner } from '../components/ErrorBanner'
import { IconExternalLink } from '../components/Icons'
import { SpeakerStrip } from '../components/SpeakerStrip'
import { Skeleton, Spinner } from '../components/Spinner'
import { StatusStamp } from '../components/StatusStamp'
import { useToast } from '../components/ToastContext'
import {
  fmtDate,
  fmtDuration,
  fmtEpNumber,
  fmtNumber,
  fmtTime,
  fmtUsd,
  safeExternalUrl,
} from '../utils/format'
import {
  buildSpeakerColorMap,
  getSpeakerColor,
  speakerDisplayName,
} from '../utils/speakers'
import './EpisodePage.css'

type EpisodeWithDates = EpisodeDetail & {
  downloaded_at?: string | null
  transcribed_at?: string | null
  indexed_at?: string | null
  summarized_at?: string | null
}

const STAGE_RANK: Record<EpisodeStatus, number> = {
  new: 0,
  downloaded: 1,
  transcribed: 2,
  indexed: 3,
}

function findSegmentIndexAtTime(segments: readonly Segment[], seconds: number): number {
  if (segments.length === 0) return -1
  for (let i = 0; i < segments.length; i += 1) {
    const seg = segments[i]!
    if (seconds >= seg.start && seconds < seg.end) {
      return i
    }
  }
  let candidate = -1
  for (let i = 0; i < segments.length; i += 1) {
    if (segments[i]!.start <= seconds) {
      candidate = i
    } else {
      break
    }
  }
  return candidate >= 0 ? candidate : 0
}

export function EpisodePage() {
  const { id: rawId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { pushToast } = useToast()

  const parsedId = rawId ? Number(rawId) : NaN
  const episodeId = Number.isFinite(parsedId) && parsedId > 0 ? parsedId : null

  const { data: config } = useConfig()
  const {
    data: episode,
    isLoading,
    error,
    refetch,
  } = useEpisode(episodeId)
  const { data: citationRefs } = useEpisodeCitations(episodeId)
  const { data: jobs } = useJobs()

  // Saved answers that cited this episode, grouped by conversation (margin back-links).
  const citedByConversation = useMemo(() => {
    const groups = new Map<number, { title: string; refs: EpisodeCitationRef[] }>()
    for (const ref of citationRefs ?? []) {
      const g = groups.get(ref.conversation_id) ?? { title: ref.conversation_title, refs: [] }
      g.refs.push(ref)
      groups.set(ref.conversation_id, g)
    }
    return [...groups.entries()]
  }, [citationRefs])

  const citeCountForSegment = useCallback(
    (seg: Segment) =>
      (citationRefs ?? []).filter((r) => r.start < seg.end && r.end > seg.start).length,
    [citationRefs],
  )

  const estimateMutation = useEstimateEpisodes()
  const processMutation = useProcessEpisodes()
  const summarizeMutation = useSummarizeEpisode()
  const reindexMutation = useReindexEpisode()
  const deleteDataMutation = useDeleteEpisodeData()

  // Playback & ?t= synchronization
  const tParam = searchParams.get('t')
  const parsedT =
    tParam !== null && tParam !== '' && Number.isFinite(Number(tParam))
      ? Math.max(0, Number(tParam))
      : null

  const [currentTime, setCurrentTime] = useState<number>(() => parsedT ?? 0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const pendingAudioSeekRef = useRef<number | null>(parsedT)
  const lastHandledTRef = useRef<string | null>(null)
  const segmentRefs = useRef<Map<number, HTMLLIElement>>(new Map())

  // Action dialogs & inline confirmations
  const [costDialogOpen, setCostDialogOpen] = useState(false)
  const [estimateData, setEstimateData] = useState<CostEstimate | null>(null)
  const [estimateErr, setEstimateErr] = useState<string | null>(null)
  const [processErr, setProcessErr] = useState<string | null>(null)

  const [pendingInlineAction, setPendingInlineAction] = useState<'summarize' | 'reindex' | null>(
    null,
  )
  const [actionError, setActionError] = useState<string | null>(null)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)

  const scrollSegmentIntoView = useCallback((segIdx: number) => {
    const el = segmentRefs.current.get(segIdx)
    if (!el) return
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({
      behavior: reduced ? 'auto' : 'smooth',
      block: 'center',
    })
  }, [])

  // Respond to ?t= on initial load or route query changes
  useEffect(() => {
    if (!episode || parsedT === null) return
    const key = `${episode.id}:${tParam}`
    if (lastHandledTRef.current === key) return
    lastHandledTRef.current = key

    setCurrentTime(parsedT)
    pendingAudioSeekRef.current = parsedT

    const audio = audioRef.current
    if (audio && audio.readyState >= 1) {
      audio.currentTime = parsedT
      pendingAudioSeekRef.current = null
    }

    if (episode.segments.length > 0) {
      const targetIdx = findSegmentIndexAtTime(episode.segments, parsedT)
      if (targetIdx >= 0) {
        window.requestAnimationFrame(() => {
          scrollSegmentIntoView(targetIdx)
        })
      }
    }
  }, [episode, parsedT, scrollSegmentIntoView, tParam])

  const seekTo = useCallback(
    (seconds: number, opts?: { scrollTranscript?: boolean; autoPlay?: boolean }) => {
      const clamped = Math.max(0, seconds)
      const secInt = Math.floor(clamped)
      setCurrentTime(clamped)

      if (episode) {
        lastHandledTRef.current = `${episode.id}:${secInt}`
      }
      setSearchParams({ t: String(secInt) }, { replace: true })

      const audio = audioRef.current
      if (audio) {
        if (audio.readyState >= 1) {
          audio.currentTime = clamped
          pendingAudioSeekRef.current = null
        } else {
          pendingAudioSeekRef.current = clamped
        }
        if (opts?.autoPlay) {
          void audio.play().catch(() => {})
        }
      }

      if (opts?.scrollTranscript && episode && episode.segments.length > 0) {
        const idx = findSegmentIndexAtTime(episode.segments, clamped)
        if (idx >= 0) {
          scrollSegmentIntoView(idx)
        }
      }
    },
    [episode, scrollSegmentIntoView, setSearchParams],
  )

  const speakerColors = useMemo(
    () =>
      episode
        ? buildSpeakerColorMap(episode.speakers, episode.segments)
        : new Map<string, string>(),
    [episode],
  )

  const activeJob = useMemo(() => {
    if (!episode || !jobs) return null
    if (episode.active_job_id !== null) {
      const byId = jobs.find((j) => j.id === episode.active_job_id)
      if (byId && isJobActive(byId)) return byId
    }
    return jobs.find((j) => j.episode_id === episode.id && isJobActive(j)) ?? null
  }, [episode, jobs])

  // Derive pipeline history dates from optional fields or completed jobs
  const historyStages = useMemo(() => {
    if (!episode) return []
    const ext = episode as EpisodeWithDates
    const rank = STAGE_RANK[episode.status]
    const epDoneJobs = (jobs ?? []).filter(
      (j) => j.episode_id === episode.id && j.status === 'done' && j.finished_at,
    )

    const findJobDate = (stepOrKind: string): string | null => {
      const match = epDoneJobs.find(
        (j) =>
          j.kind === stepOrKind ||
          (j.kind === 'process' && j.steps.includes(stepOrKind as 'download' | 'transcribe' | 'index')),
      )
      return match?.finished_at ?? null
    }

    const dlDate = ext.downloaded_at ?? findJobDate('download')
    const trDate = ext.transcribed_at ?? findJobDate('transcribe')
    const ixDate = ext.indexed_at ?? findJobDate('index') ?? findJobDate('reindex')
    const sumDate = ext.summarized_at ?? findJobDate('summarize')

    const items: Array<{ name: string; done: boolean; date: string | null }> = [
      { name: 'Downloaded', done: rank >= 1 || episode.local_audio, date: dlDate },
      { name: 'Transcribed', done: rank >= 2 || episode.segments.length > 0, date: trDate },
      { name: 'Indexed', done: rank >= 3, date: ixDate },
    ]
    if (episode.has_summary) {
      items.push({ name: 'Summarized', done: true, date: sumDate })
    }
    return items
  }, [episode, jobs])

  const activeSegmentIndex = useMemo(() => {
    if (!episode || episode.segments.length === 0) return -1
    if (currentTime <= 0 && parsedT === null) return -1
    return findSegmentIndexAtTime(episode.segments, currentTime)
  }, [currentTime, episode, parsedT])

  const totalTimelineDuration = useMemo(() => {
    if (!episode) return 0
    const lastSeg =
      episode.segments.length > 0
        ? episode.segments[episode.segments.length - 1]!.end
        : 0
    return Math.max(episode.duration_seconds ?? 0, lastSeg)
  }, [episode])

  const approxTranscriptTokens = useMemo(() => {
    if (!episode || episode.segments.length === 0) return 0
    let chars = 0
    for (const seg of episode.segments) {
      chars += seg.text.length + 12
    }
    return Math.max(100, Math.round(chars / 4))
  }, [episode])

  const openProcessDialog = async () => {
    if (!episode) return
    setCostDialogOpen(true)
    setEstimateData(null)
    setEstimateErr(null)
    setProcessErr(null)
    try {
      const est = await estimateMutation.mutateAsync({ episode_ids: [episode.id] })
      setEstimateData(est)
    } catch (err) {
      setEstimateErr(
        err instanceof ApiError ? err.detail : 'Could not fetch processing estimate.',
      )
    }
  }

  const handleConfirmProcess = () => {
    if (!episode || processMutation.isPending) return
    setProcessErr(null)
    processMutation.mutate(
      { episode_ids: [episode.id] },
      {
        onSuccess: (queued) => {
          setCostDialogOpen(false)
          pushToast({
            message:
              queued.length > 0
                ? 'Queued episode processing job.'
                : 'Episode is already indexed.',
            action: queued.length > 0 ? { label: 'View jobs', to: '/jobs' } : undefined,
          })
        },
        onError: (err) => {
          setProcessErr(err instanceof ApiError ? err.detail : 'Failed to start processing job.')
        },
      },
    )
  }

  const handleConfirmSummarize = () => {
    if (!episode || summarizeMutation.isPending) return
    setActionError(null)
    summarizeMutation.mutate(
      { id: episode.id, force: episode.has_summary },
      {
        onSuccess: () => {
          setPendingInlineAction(null)
          pushToast({
            message: 'Queued episode summary job.',
            action: { label: 'View jobs', to: '/jobs' },
          })
        },
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Could not queue summary job.')
        },
      },
    )
  }

  const handleConfirmReindex = () => {
    if (!episode || reindexMutation.isPending) return
    setActionError(null)
    reindexMutation.mutate(episode.id, {
      onSuccess: () => {
        setPendingInlineAction(null)
        pushToast({
          message: 'Queued episode re-index job.',
          action: { label: 'View jobs', to: '/jobs' },
        })
      },
      onError: (err) => {
        setActionError(err instanceof ApiError ? err.detail : 'Could not queue re-index job.')
      },
    })
  }

  const handleConfirmDeleteData = () => {
    if (!episode || deleteDataMutation.isPending) return
    deleteDataMutation.mutate(episode.id, {
      onSuccess: () => {
        setDeleteConfirmOpen(false)
        pushToast({ message: 'Deleted local audio, transcript, summary, and vectors.' })
      },
      onError: (err) => {
        setDeleteConfirmOpen(false)
        setActionError(err instanceof ApiError ? err.detail : 'Could not delete local data.')
      },
    })
  }

  if (episodeId === null) {
    return (
      <main id="main-content" className="page-container">
        <ErrorBanner
          message="Invalid episode ID."
          recovery="Return to the Library to select an episode."
        />
      </main>
    )
  }

  if (isLoading && !episode) {
    return (
      <main id="main-content" className="page-container episode-page">
        <Skeleton width="180px" height="16px" />
        <Skeleton width="78%" height="36px" />
        <Skeleton width="420px" height="18px" />
        <Skeleton width="100%" height="56px" />
        <Skeleton width="100%" height="180px" />
      </main>
    )
  }

  if (error || !episode) {
    return (
      <main id="main-content" className="page-container episode-page">
        <ErrorBanner
          message="Episode could not be loaded."
          recovery={error instanceof ApiError ? error.detail : 'Verify the episode exists.'}
          onRetry={() => void refetch()}
        />
      </main>
    )
  }

  const hasTranscript = episode.segments.length > 0
  const hasAnyLocalData =
    episode.status !== 'new' ||
    episode.local_audio ||
    hasTranscript ||
    episode.has_summary ||
    episode.passage_count > 0

  const safeRemoteAudio = safeExternalUrl(episode.audio_url)
  const speakerEntries = Object.entries(episode.speakers ?? {})

  const estSummarizeUsd = config
    ? (approxTranscriptTokens / 1_000_000) * config.prices.llm_input_per_mtok +
      (2000 / 1_000_000) * config.prices.llm_output_per_mtok
    : 0
  const estReindexUsd = config
    ? (approxTranscriptTokens / 1_000_000) * config.prices.embedding_per_mtok
    : 0

  const missingSummaryKey = Boolean(
    config &&
      !config.fake_mode &&
      ((config.llm_provider === 'openrouter' && !config.has_openrouter_key) ||
        (config.llm_provider !== 'openrouter' && !config.has_openai_key) ||
        !config.has_openai_key),
  )
  const missingOpenAiKey = Boolean(config && !config.fake_mode && !config.has_openai_key)

  return (
    <main id="main-content" className="page-container episode-page">
      {/* Breadcrumb line */}
      <nav className="episode-breadcrumb" aria-label="Breadcrumb">
        <Link to="/library">Library</Link>
        <span aria-hidden="true">·</span>
        <span>{episode.podcast_title}</span>
      </nav>

      {/* Episode header */}
      <header className="episode-header">
        <h1 className="episode-title">
          <span className="episode-catalog-num">{fmtEpNumber(episode.number)}</span>{' '}
          {episode.title}
        </h1>

        <div className="episode-meta-row">
          <span>Published {fmtDate(episode.published)}</span>
          <span aria-hidden="true">·</span>
          <span>Duration {fmtDuration(episode.duration_seconds)}</span>
          <span aria-hidden="true">·</span>
          <StatusStamp status={episode.status} />
          {episode.passage_count > 0 ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{fmtNumber(episode.passage_count)} passages</span>
            </>
          ) : null}
          {activeJob ? (
            <>
              <span aria-hidden="true">·</span>
              <Link to="/jobs" className="episode-active-job-link">
                <StatusStamp
                  status={activeJob.status}
                  progress={activeJob.status === 'running' ? activeJob.progress : undefined}
                />
              </Link>
            </>
          ) : null}
        </div>

        {/* Article-history style pipeline trail */}
        <p className="episode-history-line">
          {historyStages.map((st, idx) => (
            <span key={st.name} className="episode-history-stage-wrap">
              {idx > 0 ? (
                <span className="episode-history-sep" aria-hidden="true">
                  ·
                </span>
              ) : null}
              <span
                className={`episode-history-stage ${st.done ? 'episode-history-stage--done' : ''}`.trim()}
              >
                {st.name}
                {st.date ? ` ${fmtDate(st.date)}` : st.done ? '' : ' (pending)'}
              </span>
            </span>
          ))}
        </p>

        {/* Actions row */}
        <div className="episode-actions">
          {episode.status !== 'indexed' ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void openProcessDialog()}
            >
              Process episode
            </button>
          ) : null}

          <MakeBookButton
            episodeId={episode.id}
            disabledReason={
              hasTranscript ? undefined : 'Process and transcribe this episode before making a book'
            }
          />

          <button
            type="button"
            className="btn btn-sm"
            disabled={!hasTranscript}
            title={
              !hasTranscript
                ? 'Process and transcribe this episode before generating a summary'
                : undefined
            }
            onClick={() => {
              setActionError(null)
              setPendingInlineAction((prev) => (prev === 'summarize' ? null : 'summarize'))
            }}
          >
            {episode.has_summary ? 'Regenerate summary' : 'Generate summary'}
          </button>

          <button
            type="button"
            className="btn btn-sm"
            disabled={!hasTranscript}
            title={
              !hasTranscript
                ? 'Transcript required before re-indexing passages'
                : undefined
            }
            onClick={() => {
              setActionError(null)
              if (config?.fake_mode) {
                handleConfirmReindex()
              } else {
                setPendingInlineAction((prev) => (prev === 'reindex' ? null : 'reindex'))
              }
            }}
          >
            {reindexMutation.isPending ? <Spinner size={12} label="Queueing" /> : null}
            <span>Re-index</span>
          </button>

          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={!hasAnyLocalData}
            title={!hasAnyLocalData ? 'No local files or vectors stored for this episode' : undefined}
            onClick={() => setDeleteConfirmOpen(true)}
          >
            Delete local data
          </button>
        </div>

        {/* Inline cost note confirmation for Summarize or Re-index */}
        {pendingInlineAction === 'summarize' ? (
          <div className="episode-cost-confirm" role="region" aria-label="Confirm summary cost">
            <div className="episode-cost-confirm-body">
              <strong>Confirm summary generation</strong>
              {missingSummaryKey ? (
                <p className="episode-cost-warn">
                  Required API key (OPENAI_API_KEY / OPENROUTER_API_KEY) is not configured on the
                  server. Configure <code>.env</code> or use Demo mode.
                </p>
              ) : (
                <p>
                  Generates a structured markdown summary and indexes it alongside the transcript.
                  Model: <strong>{config?.llm_model ?? 'LLM'}</strong> · Est. cost:{' '}
                  <strong>
                    {config?.fake_mode ? '$0.00 (Demo mode)' : fmtUsd(estSummarizeUsd)}
                  </strong>{' '}
                  (~{fmtNumber(approxTranscriptTokens)} transcript tokens).
                </p>
              )}
            </div>
            <div className="episode-cost-confirm-btns">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPendingInlineAction(null)}
                disabled={summarizeMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={missingSummaryKey || summarizeMutation.isPending}
                onClick={handleConfirmSummarize}
              >
                {summarizeMutation.isPending ? <Spinner size={12} label="Queueing" /> : null}
                <span>Start summary</span>
              </button>
            </div>
          </div>
        ) : null}

        {pendingInlineAction === 'reindex' ? (
          <div className="episode-cost-confirm" role="region" aria-label="Confirm re-index cost">
            <div className="episode-cost-confirm-body">
              <strong>Confirm passage re-indexing</strong>
              {missingOpenAiKey ? (
                <p className="episode-cost-warn">
                  OPENAI_API_KEY is not configured on the server for embeddings.
                </p>
              ) : (
                <p>
                  Re-chunks the transcript and refreshes embeddings using{' '}
                  <strong>{config?.embedding_model ?? 'embeddings'}</strong> · Est. cost:{' '}
                  <strong>{fmtUsd(estReindexUsd)}</strong>.
                </p>
              )}
            </div>
            <div className="episode-cost-confirm-btns">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setPendingInlineAction(null)}
                disabled={reindexMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={missingOpenAiKey || reindexMutation.isPending}
                onClick={handleConfirmReindex}
              >
                {reindexMutation.isPending ? <Spinner size={12} label="Queueing" /> : null}
                <span>Confirm re-index</span>
              </button>
            </div>
          </div>
        ) : null}

        {actionError ? (
          <ErrorBanner
            message="Action failed."
            recovery={actionError}
            onDismiss={() => setActionError(null)}
          />
        ) : null}
      </header>

      {/* Audio & SpeakerStrip section */}
      <section className="episode-player-section" aria-label="Audio player and speaker timeline">
        {episode.local_audio ? (
          <audio
            ref={audioRef}
            controls
            preload="metadata"
            className="episode-audio"
            src={episodeAudioUrl(episode.id)}
            onLoadedMetadata={() => {
              if (pendingAudioSeekRef.current !== null && audioRef.current) {
                audioRef.current.currentTime = pendingAudioSeekRef.current
                pendingAudioSeekRef.current = null
              }
            }}
            onTimeUpdate={(e) => {
              setCurrentTime(e.currentTarget.currentTime)
            }}
          />
        ) : (
          <div className="episode-no-audio">
            <span>Local audio has not been downloaded for this episode yet.</span>
            {safeRemoteAudio ? (
              <a
                href={safeRemoteAudio}
                target="_blank"
                rel="noopener noreferrer"
                className="episode-remote-link"
              >
                <span>Open original feed audio</span>
                <IconExternalLink size={12} />
              </a>
            ) : null}
          </div>
        )}

        {hasTranscript ? (
          <div className="episode-strip-block">
            {speakerEntries.length > 0 ? (
              <div className="episode-speaker-legend" aria-label="Speakers">
                {speakerEntries.map(([label, name]) => (
                  <span key={label} className="episode-legend-item">
                    <span
                      className="episode-legend-swatch"
                      style={{ backgroundColor: getSpeakerColor(label, speakerColors) }}
                      aria-hidden="true"
                    />
                    <span>{name}</span>
                  </span>
                ))}
              </div>
            ) : null}

            <SpeakerStrip
              segments={episode.segments}
              speakers={episode.speakers}
              colorMap={speakerColors}
              windowStart={0}
              windowEnd={totalTimelineDuration}
              currentTime={currentTime}
              onSeek={(sec) => seekTo(sec, { scrollTranscript: true, autoPlay: episode.local_audio })}
              variant="full"
              hint={
                episode.local_audio
                  ? 'Click the timeline to seek the audio'
                  : 'Click the timeline to jump to that point in the transcript'
              }
            />
          </div>
        ) : null}
      </section>

      {/* Optional Summary Panel */}
      {episode.summary_markdown ? (
        <section className="episode-summary-section" aria-labelledby="summary-heading">
          <h2 id="summary-heading" className="episode-section-heading">
            Summary
          </h2>
          <div className="episode-summary-prose">
            <Markdown>{episode.summary_markdown}</Markdown>
          </div>
        </section>
      ) : null}

      {/* Diarized Transcript */}
      <section className="episode-transcript-section" aria-labelledby="transcript-heading">
        <div className="episode-transcript-head">
          <h2 id="transcript-heading" className="episode-section-heading">
            Transcript
            {hasTranscript ? (
              <span className="episode-seg-count">
                {fmtNumber(episode.segments.length)} segments
              </span>
            ) : null}
          </h2>
        </div>

        {!hasTranscript ? (
          <EmptyState
            title="No transcript yet"
            description="Process this episode to download the audio, diarize speaker turns with timestamps, and index passages for chat."
            action={
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void openProcessDialog()}
              >
                Process episode
              </button>
            }
          />
        ) : (
          <div className="episode-transcript-layout">
          <ol className="episode-segments">
            {episode.segments.map((seg, idx) => {
              const isCurrent = idx === activeSegmentIndex
              const citeCount = citeCountForSegment(seg)
              const spColor = getSpeakerColor(seg.speaker, speakerColors)
              const spName = speakerDisplayName(seg.speaker, episode.speakers)

              return (
                <li
                  key={`${idx}-${seg.start}`}
                  ref={(node) => {
                    if (node) {
                      segmentRefs.current.set(idx, node)
                    } else {
                      segmentRefs.current.delete(idx)
                    }
                  }}
                  className={`episode-seg ${isCurrent ? 'episode-seg--active' : ''}`.trim()}
                >
                  <div className="episode-seg-gutter">
                    <button
                      type="button"
                      className="episode-ts-btn"
                      onClick={() =>
                        seekTo(seg.start, {
                          scrollTranscript: false,
                          autoPlay: episode.local_audio,
                        })
                      }
                      aria-label={`Seek to ${fmtTime(seg.start)}, ${spName}`}
                    >
                      {fmtTime(seg.start)}
                    </button>
                    {citeCount > 0 ? (
                      <span
                        className="episode-seg-cited"
                        title={`Cited in ${citeCount} saved answer${citeCount === 1 ? '' : 's'}`}
                      >
                        cited{citeCount > 1 ? ` ${citeCount}` : ''}
                      </span>
                    ) : null}
                  </div>
                  <p className="episode-seg-text">
                    <span className="episode-seg-speaker" style={{ color: spColor }}>
                      {spName}
                    </span>{' '}
                    {seg.text}
                  </p>
                </li>
              )
            })}
          </ol>

          <aside className="episode-cited-margin" aria-labelledby="cited-heading">
            <h3 id="cited-heading" className="episode-cited-heading">
              Cited in your conversations
            </h3>
            {citedByConversation.length === 0 ? (
              <p className="episode-cited-empty">
                No saved answer cites this episode yet. Ask about it in Chat and the passages
                used will be marked here.
              </p>
            ) : (
              <ul className="episode-cited-list">
                {citedByConversation.map(([convId, group]) => (
                  <li key={convId} className="episode-cited-group">
                    <Link to={`/chat/${convId}`} className="episode-cited-conv">
                      {group.title}
                    </Link>
                    <span className="episode-cited-times">
                      {group.refs.map((ref) => (
                        <button
                          key={`${ref.message_id}-${ref.n}`}
                          type="button"
                          className="episode-cited-time"
                          onClick={() => seekTo(ref.start, { scrollTranscript: true })}
                          aria-label={`Jump to ${fmtTime(ref.start)}, cited as [${ref.n}] by ${ref.speaker || 'speaker'}`}
                        >
                          [{ref.n}] {fmtTime(ref.start)}
                        </button>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </aside>
          </div>
        )}
      </section>

      <CostConfirmDialog
        open={costDialogOpen}
        config={config}
        estimate={estimateData}
        estimating={estimateMutation.isPending}
        estimateError={estimateErr}
        submitting={processMutation.isPending}
        submitError={processErr}
        onRetryEstimate={() => void openProcessDialog()}
        onConfirm={handleConfirmProcess}
        onClose={() => {
          if (!processMutation.isPending) setCostDialogOpen(false)
        }}
      />

      <ConfirmDialog
        open={deleteConfirmOpen}
        title="Delete local episode data"
        description={`Delete the local audio file, diarized transcript, summary, and indexed passages for "${episode.title}"? The episode entry from the RSS feed will remain so you can process it again later.`}
        confirmLabel="Delete local data"
        danger
        busy={deleteDataMutation.isPending}
        onConfirm={handleConfirmDeleteData}
        onClose={() => {
          if (!deleteDataMutation.isPending) setDeleteConfirmOpen(false)
        }}
      />
    </main>
  )
}
