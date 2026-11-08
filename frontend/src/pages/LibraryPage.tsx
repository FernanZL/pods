import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  isJobActive,
  useConfig,
  useDeletePodcast,
  useEpisodes,
  useEstimateEpisodes,
  useJobs,
  usePodcasts,
  useProcessEpisodes,
  useRefreshPodcast,
} from '../api/hooks'
import type {
  CostEstimate,
  Episode,
  EpisodeStatus,
  Job,
  Podcast,
  SelectionRequest,
} from '../api/types'
import { BrowsePodcasts } from '../components/BrowsePodcasts'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { CostConfirmDialog } from '../components/CostConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import {
  IconArrowLeft,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconUpload,
} from '../components/Icons'
import { Skeleton, Spinner } from '../components/Spinner'
import { StatusStamp } from '../components/StatusStamp'
import { useToast } from '../components/ToastContext'
import { UploadDialog } from '../components/UploadDialog'
import { fmtDate, fmtDuration, fmtEpNumber, fmtNumber } from '../utils/format'
import { isUploadShow } from '../utils/podcasts'
import { buildSpeakerColorMap, getSpeakerColor } from '../utils/speakers'
import './LibraryPage.css'

const PAGE_SIZE = 50

export function LibraryPage() {
  const { pushToast } = useToast()
  const { data: config } = useConfig()
  const {
    data: podcasts,
    isLoading: podcastsLoading,
    error: podcastsError,
    refetch: refetchPodcasts,
  } = usePodcasts()
  const { data: jobs } = useJobs()

  // Feed management state
  const [feedError, setFeedError] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<number | null>(null)
  const [deletingPodcast, setDeletingPodcast] = useState<Podcast | null>(null)

  // Views: "Your library" (episodes already collected), one show's full catalog
  // (?show=<id>, where new episodes are picked), and "Browse podcasts" (?tab=browse).
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') === 'browse' ? 'browse' : 'library'
  const showParam = Number(searchParams.get('show'))
  const showId = tab === 'library' && Number.isInteger(showParam) && showParam > 0 ? showParam : null
  const catalog = showId !== null
  const catalogPodcast = catalog ? podcasts?.find((p) => p.id === showId) : undefined
  const setTab = (next: 'library' | 'browse') => {
    const params = new URLSearchParams(searchParams)
    if (next === 'browse') params.set('tab', 'browse')
    else params.delete('tab')
    params.delete('show')
    setSearchParams(params, { replace: true })
  }
  const openShow = (id: number) => {
    const params = new URLSearchParams(searchParams)
    params.delete('tab')
    params.set('show', String(id))
    setSearchParams(params)
  }
  const closeShow = () => {
    const params = new URLSearchParams(searchParams)
    params.delete('show')
    setSearchParams(params)
  }
  const [uploadOpen, setUploadOpen] = useState(false)
  const refreshPodcast = useRefreshPodcast()
  const deletePodcast = useDeletePodcast()

  // Episode filters & pagination
  const [podcastFilter, setPodcastFilter] = useState<number | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [searchDesc, setSearchDesc] = useState(false)
  const [statusFilter, setStatusFilter] = useState<EpisodeStatus | ''>('')
  const [page, setPage] = useState(0)

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
  const [allMatchingSelected, setAllMatchingSelected] = useState(false)
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null)

  // Cost estimation & processing modal state
  const [costDialogOpen, setCostDialogOpen] = useState(false)
  const [pendingSelection, setPendingSelection] = useState<SelectionRequest | null>(null)
  const [estimateData, setEstimateData] = useState<CostEstimate | null>(null)
  const [estimateErr, setEstimateErr] = useState<string | null>(null)
  const [processErr, setProcessErr] = useState<string | null>(null)
  const [resolvingSelection, setResolvingSelection] = useState(false)

  const estimateMutation = useEstimateEpisodes()
  const processMutation = useProcessEpisodes()

  // Switching between the library and a show's catalog starts from a clean slate.
  const [viewShowId, setViewShowId] = useState(showId)
  if (viewShowId !== showId) {
    setViewShowId(showId)
    setPage(0)
    setSelectedIds(new Set())
    setAllMatchingSelected(false)
    setStatusFilter('')
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQ(searchInput.trim())
      setPage(0)
      setAllMatchingSelected(false)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const episodesFilter = useMemo(
    () => ({
      podcast_id: catalog ? showId : podcastFilter,
      q: debouncedQ || undefined,
      search_description: searchDesc,
      status: statusFilter,
      collected: !catalog,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [catalog, debouncedQ, page, podcastFilter, searchDesc, showId, statusFilter],
  )

  const {
    data: episodeList,
    isLoading: episodesLoading,
    error: episodesError,
    refetch: refetchEpisodes,
  } = useEpisodes(episodesFilter)

  const activeJobsByEpisode = useMemo(() => {
    const map = new Map<number, Job>()
    if (!jobs) return map
    for (const job of jobs) {
      if (job.episode_id !== null && isJobActive(job) && !map.has(job.episode_id)) {
        map.set(job.episode_id, job)
      }
    }
    return map
  }, [jobs])

  const activeJobsById = useMemo(() => {
    const map = new Map<number, Job>()
    if (!jobs) return map
    for (const job of jobs) {
      map.set(job.id, job)
    }
    return map
  }, [jobs])

  const pageItems = episodeList?.items ?? []
  const totalMatching = episodeList?.total ?? 0

  const allPageSelected =
    pageItems.length > 0 &&
    (allMatchingSelected || pageItems.every((ep) => selectedIds.has(ep.id)))
  const somePageSelected =
    !allPageSelected && pageItems.some((ep) => selectedIds.has(ep.id))

  useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate = somePageSelected
    }
  }, [somePageSelected])

  const selectedCount = allMatchingSelected ? totalMatching : selectedIds.size

  const handleRefreshPodcast = (podcast: Podcast) => {
    setFeedError(null)
    setRefreshingId(podcast.id)
    refreshPodcast.mutate(podcast.id, {
      onSuccess: (updated) => {
        setRefreshingId(null)
        pushToast({
          message: `Refreshed "${updated.title}" (${fmtNumber(updated.episode_count)} episodes).`,
        })
      },
      onError: (err) => {
        setRefreshingId(null)
        setFeedError(
          err instanceof ApiError ? err.detail : `Could not refresh "${podcast.title}".`,
        )
      },
    })
  }

  const handleConfirmDeletePodcast = () => {
    if (!deletingPodcast) return
    const target = deletingPodcast
    deletePodcast.mutate(
      { id: target.id, deleteFiles: true },
      {
        onSuccess: () => {
          setDeletingPodcast(null)
          if (podcastFilter === target.id) {
            setPodcastFilter(null)
          }
          if (showId === target.id) {
            closeShow()
          }
          clearSelection()
          pushToast({ message: `Removed "${target.title}".` })
        },
        onError: (err) => {
          setDeletingPodcast(null)
          setFeedError(err instanceof ApiError ? err.detail : 'Could not remove podcast feed.')
        },
      },
    )
  }

  const toggleRow = (id: number) => {
    if (allMatchingSelected) {
      // Materialize current page minus this row
      const next = new Set(pageItems.map((ep) => ep.id))
      next.delete(id)
      setAllMatchingSelected(false)
      setSelectedIds(next)
      return
    }
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const togglePage = () => {
    if (allPageSelected) {
      if (allMatchingSelected) {
        setAllMatchingSelected(false)
        setSelectedIds(new Set())
        return
      }
      setSelectedIds((prev) => {
        const next = new Set(prev)
        for (const ep of pageItems) {
          next.delete(ep.id)
        }
        return next
      })
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        for (const ep of pageItems) {
          next.add(ep.id)
        }
        return next
      })
    }
  }

  const clearSelection = () => {
    setAllMatchingSelected(false)
    setSelectedIds(new Set())
  }

  const buildSelection = (): SelectionRequest => {
    if (allMatchingSelected) {
      return {
        podcast_id: catalog ? showId : podcastFilter,
        q: debouncedQ || null,
        search_description: searchDesc,
        status: statusFilter || null,
        collected: !catalog,
      }
    }
    return {
      episode_ids: Array.from(selectedIds),
    }
  }

  const runEstimate = async (selection?: SelectionRequest) => {
    setCostDialogOpen(true)
    setEstimateData(null)
    setEstimateErr(null)
    setProcessErr(null)
    setResolvingSelection(true)

    try {
      const sel = selection ?? buildSelection()
      setPendingSelection(sel)
      setResolvingSelection(false)
      const est = await estimateMutation.mutateAsync(sel)
      setEstimateData(est)
    } catch (err) {
      setResolvingSelection(false)
      setEstimateErr(
        err instanceof ApiError ? err.detail : 'Failed to request cost estimate from server.',
      )
    }
  }

  const handleConfirmProcess = () => {
    if (!pendingSelection || processMutation.isPending) return
    setProcessErr(null)
    processMutation.mutate(pendingSelection, {
      onSuccess: (queuedJobs) => {
        setCostDialogOpen(false)
        clearSelection()
        pushToast({
          message:
            queuedJobs.length > 0
              ? `Queued ${fmtNumber(queuedJobs.length)} ${queuedJobs.length === 1 ? 'episode job' : 'episode jobs'}.`
              : 'All selected episodes were already processed.',
          action: queuedJobs.length > 0 ? { label: 'View jobs', to: '/jobs' } : undefined,
        })
      },
      onError: (err) => {
        setProcessErr(err instanceof ApiError ? err.detail : 'Could not enqueue processing jobs.')
      },
    })
  }

  const handleUploaded = (episode: Episode) => {
    setUploadOpen(false)
    pushToast({
      message: `Uploaded "${episode.title}" to ${episode.podcast_title}.`,
      action: { label: 'Open', to: `/episodes/${episode.id}` },
    })
    if (tab === 'browse' || catalog) setTab('library')
    // Straight to the cost check, so the file can be transcribed and indexed now.
    void runEstimate({ episode_ids: [episode.id] })
  }

  const filtersActive = Boolean(debouncedQ) || statusFilter !== '' || podcastFilter !== null
  const totalPages = Math.max(1, Math.ceil(totalMatching / PAGE_SIZE))
  const rangeStart = totalMatching === 0 ? 0 : page * PAGE_SIZE + 1
  const rangeEnd = Math.min(totalMatching, (page + 1) * PAGE_SIZE)

  return (
    <main id="main-content" className="page-container library-page">
      <div className="page-header">
        <h1 className="page-title">Library</h1>
        <span className="library-header-note">
          Episodes you have collected. Open a show to pick more, find new podcasts, or upload a file.
        </span>
      </div>

      <div className="library-tabs" role="tablist" aria-label="Library views">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'library'}
          className={`library-tab ${tab === 'library' ? 'library-tab--on' : ''}`.trim()}
          onClick={() => setTab('library')}
        >
          Your library
          {podcasts && podcasts.length > 0 ? (
            <span className="library-tab-count">{fmtNumber(podcasts.length)}</span>
          ) : null}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'browse'}
          className={`library-tab ${tab === 'browse' ? 'library-tab--on' : ''}`.trim()}
          onClick={() => setTab('browse')}
        >
          Browse podcasts
        </button>
      </div>

      {tab === 'browse' ? (
        <BrowsePodcasts
          onOpenInLibrary={(id) => openShow(id)}
          onAdded={(created) => {
            pushToast({
              message: `Added "${created.title}" (${fmtNumber(created.episode_count)} episodes). Pick the ones to process.`,
            })
            openShow(created.id)
          }}
          onUpload={() => setUploadOpen(true)}
        />
      ) : (
      <>
      {catalog ? (
        /* One show's full catalog: where new episodes are picked for the library */
        <section className="library-catalog-head" aria-labelledby="catalog-heading">
          <button type="button" className="btn btn-ghost btn-sm library-back" onClick={closeShow}>
            <IconArrowLeft size={13} />
            <span>Your library</span>
          </button>
          <div className="library-catalog-bar">
            <div className="library-catalog-title">
              <h2 id="catalog-heading" className="library-catalog-name">
                {catalogPodcast?.title ?? (podcastsLoading ? 'Loading…' : 'Show not found')}
              </h2>
              {catalogPodcast ? (
                <span className="library-feed-meta">
                  {isUploadShow(catalogPodcast)
                    ? `${fmtNumber(catalogPodcast.episode_count)} uploaded ${catalogPodcast.episode_count === 1 ? 'file' : 'files'}`
                    : `${fmtNumber(catalogPodcast.episode_count)} episodes in the feed · Refreshed ${fmtDate(catalogPodcast.refreshed_at)}`}
                  {' · '}
                  {fmtNumber(catalogPodcast.indexed_count)} indexed
                </span>
              ) : null}
            </div>
            {catalogPodcast ? (
              <div className="library-feed-actions">
                {isUploadShow(catalogPodcast) ? (
                  <button type="button" className="btn btn-sm" onClick={() => setUploadOpen(true)}>
                    <IconUpload size={13} />
                    <span>Upload another</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={refreshingId === catalogPodcast.id && refreshPodcast.isPending}
                    onClick={() => handleRefreshPodcast(catalogPodcast)}
                  >
                    {refreshingId === catalogPodcast.id && refreshPodcast.isPending ? (
                      <Spinner size={12} label="Refreshing" />
                    ) : (
                      <IconRefresh size={13} />
                    )}
                    <span>Refresh</span>
                  </button>
                )}
              </div>
            ) : null}
          </div>
          {feedError ? (
            <ErrorBanner
              message="Feed action failed."
              recovery={feedError}
              onDismiss={() => setFeedError(null)}
            />
          ) : null}
        </section>
      ) : (
      /* Shows the owner follows; each opens its full catalog */
      <section className="library-feeds-section" aria-labelledby="feeds-heading">
        <div className="library-feeds-bar">
          <h2 id="feeds-heading" className="library-section-heading">
            Your shows
          </h2>

          <div className="library-feed-actions">
            <button type="button" className="btn btn-sm" onClick={() => setUploadOpen(true)}>
              <IconUpload size={12} />
              <span>Upload audio</span>
            </button>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setTab('browse')}>
              <IconPlus size={12} />
              <span>Find podcasts</span>
            </button>
          </div>
        </div>

        {feedError ? (
          <ErrorBanner
            message="Feed action failed."
            recovery={feedError}
            onDismiss={() => setFeedError(null)}
          />
        ) : null}

        {podcastsError ? (
          <ErrorBanner
            message="Could not load podcast feeds."
            recovery={podcastsError instanceof ApiError ? podcastsError.detail : undefined}
            onRetry={() => void refetchPodcasts()}
          />
        ) : podcastsLoading && !podcasts ? (
          <div className="library-feed-skeletons">
            <Skeleton height="42px" />
          </div>
        ) : !podcasts || podcasts.length === 0 ? (
          <div className="library-feeds-empty">
            <p>
              No shows yet. Use <strong>Find podcasts</strong> to search the directory by name
              (for example Huberman Lab), or <strong>Upload audio</strong> to add a file from
              this computer.
            </p>
          </div>
        ) : (
          <ul className="library-feed-list">
            {podcasts.map((p) => {
              const isRefreshing = refreshingId === p.id && refreshPodcast.isPending
              const upload = isUploadShow(p)
              return (
                <li key={p.id} className="library-feed-row">
                  <div className="library-feed-main">
                    <button
                      type="button"
                      className="library-feed-title-btn"
                      onClick={() => openShow(p.id)}
                    >
                      {p.title}
                    </button>
                    <span className="library-feed-meta">
                      {upload
                        ? `${fmtNumber(p.episode_count)} uploaded ${p.episode_count === 1 ? 'file' : 'files'}`
                        : `${fmtNumber(p.episode_count)} episodes`}{' '}
                      · {fmtNumber(p.indexed_count)} indexed
                      {upload ? '' : ` · Refreshed ${fmtDate(p.refreshed_at)}`}
                    </span>
                  </div>
                  <div className="library-feed-actions">
                    <button type="button" className="btn btn-sm" onClick={() => openShow(p.id)}>
                      <span>{upload ? 'Files' : 'Browse episodes'}</span>
                    </button>
                    {upload ? null : (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={isRefreshing}
                        onClick={() => handleRefreshPodcast(p)}
                        aria-label={`Refresh ${p.title}`}
                      >
                        {isRefreshing ? (
                          <Spinner size={12} label="Refreshing" />
                        ) : (
                          <IconRefresh size={13} />
                        )}
                        <span>Refresh</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm library-feed-remove"
                      onClick={() => setDeletingPodcast(p)}
                      aria-label={`Remove ${p.title}`}
                    >
                      <IconTrash size={13} />
                      <span>Remove</span>
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>
      )}

      {/* Episodes: the collected library, or the open show's catalog */}
      <section className="library-episodes-section" aria-labelledby="episodes-heading">
        <div className="library-filters-bar">
          <h2 id="episodes-heading" className="library-section-heading">
            {catalog ? 'All episodes' : 'Your episodes'}
            <span className="library-total-count">{fmtNumber(totalMatching)}</span>
          </h2>

          <div className="library-filters-controls">
            {catalog ? null : (
              <div className="library-filter-item">
                <label htmlFor="filter-podcast" className="sr-only">
                  Filter by show
                </label>
                <select
                  id="filter-podcast"
                  className="select select-sm"
                  value={podcastFilter ?? ''}
                  onChange={(e) => {
                    const val = e.target.value
                    setPodcastFilter(val ? Number(val) : null)
                    setPage(0)
                    setAllMatchingSelected(false)
                  }}
                >
                  <option value="">All shows</option>
                  {podcasts?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="library-search-wrap">
              <IconSearch size={14} className="library-search-icon" />
              <label htmlFor="filter-episode-q" className="sr-only">
                Search episodes
              </label>
              <input
                id="filter-episode-q"
                type="search"
                className="input input-sm library-search-input"
                placeholder="Search title…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>

            <label className="library-desc-toggle">
              <input
                type="checkbox"
                className="checkbox"
                checked={searchDesc}
                onChange={(e) => {
                  setSearchDesc(e.target.checked)
                  setPage(0)
                  setAllMatchingSelected(false)
                }}
              />
              <span>Also search descriptions</span>
            </label>

            <div className="library-filter-item">
              <label htmlFor="filter-status" className="sr-only">
                Filter by status
              </label>
              <select
                id="filter-status"
                className="select select-sm"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value as EpisodeStatus | '')
                  setPage(0)
                  setAllMatchingSelected(false)
                }}
              >
                <option value="">All statuses</option>
                {catalog ? <option value="new">Not processed</option> : null}
                <option value="downloaded">Downloaded</option>
                <option value="transcribed">Transcribed</option>
                <option value="indexed">Indexed</option>
              </select>
            </div>
          </div>
        </div>

        {catalog && catalogPodcast && !isUploadShow(catalogPodcast) ? (
          <p className="library-catalog-hint">
            Tick the episodes you want and process them. They join your library as soon as they
            are queued.
          </p>
        ) : null}

        {/* Selection action bar */}
        {selectedCount > 0 ? (
          <div className="library-selection-bar" role="region" aria-label="Selected episodes actions">
            <div className="library-selection-info">
              <strong>
                {fmtNumber(selectedCount)} {selectedCount === 1 ? 'episode' : 'episodes'} selected
              </strong>
              {allPageSelected && !allMatchingSelected && totalMatching > pageItems.length ? (
                <button
                  type="button"
                  className="library-select-all-link"
                  onClick={() => setAllMatchingSelected(true)}
                >
                  Select all {fmtNumber(totalMatching)} matching
                </button>
              ) : null}
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearSelection}>
                Clear
              </button>
            </div>

            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void runEstimate()}
            >
              Process {fmtNumber(selectedCount)} {selectedCount === 1 ? 'episode' : 'episodes'}
            </button>
          </div>
        ) : null}

        {episodesError ? (
          <ErrorBanner
            message="Could not load episodes."
            recovery={episodesError instanceof ApiError ? episodesError.detail : undefined}
            onRetry={() => void refetchEpisodes()}
          />
        ) : episodesLoading && !episodeList ? (
          <div className="library-table-skeletons">
            <Skeleton height="38px" />
            <Skeleton height="38px" />
            <Skeleton height="38px" />
            <Skeleton height="38px" />
            <Skeleton height="38px" />
          </div>
        ) : pageItems.length === 0 ? (
          catalog || filtersActive ? (
            <EmptyState
              title="No matching episodes"
              description={
                catalog && !filtersActive
                  ? 'This show has no episodes yet. Try refreshing its feed.'
                  : 'Adjust your search query or filters to see episodes.'
              }
            />
          ) : (
            <EmptyState
              title={
                podcasts && podcasts.length > 0
                  ? 'No episodes in your library yet'
                  : 'Your library is empty'
              }
              description={
                podcasts && podcasts.length > 0
                  ? 'Open one of your shows above to browse its episodes, then process the ones you want. They appear here once they are downloaded.'
                  : 'Find a podcast or upload an audio file, then pick the episodes to process.'
              }
              action={
                podcasts && podcasts.length === 1 ? (
                  <button type="button" className="btn btn-primary" onClick={() => openShow(podcasts[0].id)}>
                    Browse {podcasts[0].title}
                  </button>
                ) : podcasts && podcasts.length > 1 ? null : (
                  <button type="button" className="btn btn-primary" onClick={() => setTab('browse')}>
                    Find podcasts
                  </button>
                )
              }
            />
          )
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table library-table">
                <thead>
                  <tr>
                    <th className="library-col-check">
                      <input
                        ref={headerCheckboxRef}
                        type="checkbox"
                        className="checkbox"
                        checked={allPageSelected}
                        onChange={togglePage}
                        aria-label="Select all episodes on this page"
                      />
                    </th>
                    <th className="library-col-ep">Ep.</th>
                    <th>Title</th>
                    <th className="library-col-dur">Duration</th>
                    <th className="library-col-speakers">Speakers</th>
                    <th className="library-col-status">Status</th>
                    <th className="library-col-passages">Passages</th>
                    <th className="library-col-job">Job</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((ep) => {
                    const checked = allMatchingSelected || selectedIds.has(ep.id)
                    const activeJob =
                      (ep.active_job_id !== null ? activeJobsById.get(ep.active_job_id) : undefined) ??
                      activeJobsByEpisode.get(ep.id)
                    const speakerEntries = Object.entries(ep.speakers ?? {})
                    const spColors = buildSpeakerColorMap(ep.speakers)

                    return (
                      <tr
                        key={ep.id}
                        className={checked ? 'library-row--selected' : undefined}
                      >
                        <td className="library-col-check">
                          <input
                            type="checkbox"
                            className="checkbox"
                            checked={checked}
                            onChange={() => toggleRow(ep.id)}
                            aria-label={`Select ${fmtEpNumber(ep.number)} ${ep.title}`}
                          />
                        </td>
                        <td className="library-col-ep">{fmtEpNumber(ep.number)}</td>
                        <td className="library-col-title">
                          <Link
                            to={`/episodes/${ep.id}`}
                            className="library-ep-link"
                            title={ep.title}
                          >
                            {ep.title}
                          </Link>
                          <span className="library-ep-sub">
                            {!catalog && podcasts && podcasts.length > 1 ? `${ep.podcast_title} · ` : ''}
                            {fmtDate(ep.published)}
                          </span>
                          <span className="library-ep-mobile-meta">
                            <span>{fmtDuration(ep.duration_seconds)}</span>
                            <StatusStamp status={ep.status} />
                          </span>
                        </td>
                        <td className="library-col-dur">{fmtDuration(ep.duration_seconds)}</td>
                        <td className="library-col-speakers">
                          {speakerEntries.length > 0 ? (
                            <span className="library-speakers-list">
                              {speakerEntries.slice(0, 3).map(([label, name]) => (
                                <span key={label} className="library-speaker-pill">
                                  <span
                                    className="library-speaker-dot"
                                    style={{
                                      backgroundColor: getSpeakerColor(label, spColors),
                                    }}
                                    aria-hidden="true"
                                  />
                                  {name}
                                </span>
                              ))}
                              {speakerEntries.length > 3 ? (
                                <span className="library-speaker-more">
                                  +{speakerEntries.length - 3}
                                </span>
                              ) : null}
                            </span>
                          ) : (
                            <span className="library-cell-faint">—</span>
                          )}
                        </td>
                        <td className="library-col-status">
                          <StatusStamp status={ep.status} />
                        </td>
                        <td className="library-col-passages">
                          {ep.passage_count > 0 ? (
                            fmtNumber(ep.passage_count)
                          ) : (
                            <span className="library-cell-faint">—</span>
                          )}
                        </td>
                        <td className="library-col-job">
                          {activeJob ? (
                            <Link to="/jobs" className="library-job-cell">
                              <StatusStamp
                                status={activeJob.status}
                                progress={
                                  activeJob.status === 'running' ? activeJob.progress : undefined
                                }
                              />
                              <span className="library-job-bar" aria-hidden="true">
                                <span
                                  className="library-job-bar-fill"
                                  style={{
                                    width: `${Math.round(Math.max(0, Math.min(1, activeJob.progress)) * 100)}%`,
                                  }}
                                />
                              </span>
                            </Link>
                          ) : (
                            <span className="library-cell-faint">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="library-pagination">
              <span className="library-pagination-meta">
                Showing {fmtNumber(rangeStart)}–{fmtNumber(rangeEnd)} of {fmtNumber(totalMatching)}
              </span>
              <div className="library-pagination-btns">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Previous
                </button>
                <span className="library-page-indicator">
                  Page {fmtNumber(page + 1)} of {fmtNumber(totalPages)}
                </span>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
      </>
      )}

      <UploadDialog
        open={uploadOpen}
        podcasts={podcasts}
        onClose={() => setUploadOpen(false)}
        onUploaded={handleUploaded}
      />

      <CostConfirmDialog
        open={costDialogOpen}
        config={config}
        estimate={estimateData}
        estimating={resolvingSelection || estimateMutation.isPending}
        estimateError={estimateErr}
        submitting={processMutation.isPending}
        submitError={processErr}
        onRetryEstimate={() => void runEstimate(pendingSelection ?? undefined)}
        onConfirm={handleConfirmProcess}
        onClose={() => {
          if (!processMutation.isPending) {
            setCostDialogOpen(false)
          }
        }}
      />

      <ConfirmDialog
        open={deletingPodcast !== null}
        title="Remove show"
        description={
          deletingPodcast
            ? `Remove "${deletingPodcast.title}" and delete its ${fmtNumber(deletingPodcast.episode_count)} episodes, indexed passages, and local files?`
            : ''
        }
        confirmLabel="Remove show"
        danger
        busy={deletePodcast.isPending}
        onConfirm={handleConfirmDeletePodcast}
        onClose={() => {
          if (!deletePodcast.isPending) setDeletingPodcast(null)
        }}
      />
    </main>
  )
}
