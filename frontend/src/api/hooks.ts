import { useEffect, useRef } from 'react'
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  cancelJob,
  checkEpisode,
  createBook,
  deleteBook,
  estimateBook,
  getBooks,
  reshuffleBook,
  clearFinishedJobs,
  deleteJob,
  getDiscoverGenres,
  getTopPodcasts,
  searchDirectory,
  createPodcast,
  deleteConversation,
  deleteEpisodeData,
  deletePodcast,
  estimateEpisodes,
  getConfig,
  getConversation,
  getConversations,
  getEpisode,
  getEpisodeCitations,
  getEpisodes,
  getIndexStats,
  getJobs,
  getPodcasts,
  patchConversation,
  processEpisodes,
  rebuildIndex,
  refreshPodcast,
  reindexEpisode,
  retryJob,
  summarizeEpisode,
  type EpisodesFilter,
  type JobsFilter,
} from './client'
import type { ConversationPatch, EpisodeDetail, Job, SelectionRequest } from './types'

export const queryKeys = {
  config: ['config'] as const,
  indexStats: ['indexStats'] as const,
  podcasts: ['podcasts'] as const,
  episodes: (filter?: EpisodesFilter) => ['episodes', filter ?? {}] as const,
  episodesAll: ['episodes'] as const,
  episode: (id: number) => ['episode', id] as const,
  episodeAll: ['episode'] as const,
  episodeCitations: (id: number) => ['episodeCitations', id] as const,
  books: ['books'] as const,
  discoverGenres: ['discoverGenres'] as const,
  discoverSearch: (q: string) => ['discoverSearch', q] as const,
  discoverTop: (genreId: number | null) => ['discoverTop', genreId] as const,
  discoverAll: ['discoverSearch'] as const,
  jobs: (filter?: JobsFilter) => ['jobs', filter ?? {}] as const,
  jobsAll: ['jobs'] as const,
  conversations: ['conversations'] as const,
  conversation: (id: number) => ['conversation', id] as const,
}

/** Saved answers that cited this episode (transcript back-links). */
export function useEpisodeCitations(id: number | null) {
  return useQuery({
    queryKey: queryKeys.episodeCitations(id ?? 0),
    queryFn: () => getEpisodeCitations(id!),
    enabled: id !== null && Number.isFinite(id) && id > 0,
  })
}

export function isJobActive(job: Pick<Job, 'status'>): boolean {
  return job.status === 'queued' || job.status === 'running'
}

export function useConfig() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: getConfig,
    staleTime: 60_000,
  })
}

export function useIndexStats() {
  return useQuery({
    queryKey: queryKeys.indexStats,
    queryFn: getIndexStats,
  })
}

export function usePodcasts() {
  return useQuery({
    queryKey: queryKeys.podcasts,
    queryFn: getPodcasts,
  })
}

export function useEpisodes(filter?: EpisodesFilter) {
  return useQuery({
    queryKey: queryKeys.episodes(filter),
    queryFn: () => getEpisodes(filter),
    placeholderData: keepPreviousData,
  })
}

export function useEpisode(id: number | null) {
  return useQuery({
    queryKey: queryKeys.episode(id ?? 0),
    queryFn: () => getEpisode(id!),
    enabled: id !== null && Number.isFinite(id) && id > 0,
  })
}

/** Load EpisodeDetail in parallel for unique episode IDs referenced in citations. */
export function useCitedEpisodes(episodeIds: readonly number[]): ReadonlyMap<number, EpisodeDetail> {
  const uniqueIds = Array.from(new Set(episodeIds.filter((id) => Number.isFinite(id) && id > 0)))
  const results = useQueries({
    queries: uniqueIds.map((id) => ({
      queryKey: queryKeys.episode(id),
      queryFn: () => getEpisode(id),
      staleTime: 60_000,
    })),
  })

  const map = new Map<number, EpisodeDetail>()
  results.forEach((res, idx) => {
    const id = uniqueIds[idx]
    if (id !== undefined && res.data) {
      map.set(id, res.data)
    }
  })
  return map
}

/**
 * Fetch background jobs, polling every 2 seconds ONLY while any job is queued or running.
 * Automatically invalidates episode and index queries whenever an active job finishes.
 */
export function useJobs(filter?: JobsFilter) {
  const queryClient = useQueryClient()
  const prevActiveIdsRef = useRef<Set<number>>(new Set())

  const query = useQuery({
    queryKey: queryKeys.jobs(filter),
    queryFn: () => getJobs(filter),
    refetchInterval: (q) => {
      const data = q.state.data
      if (!data) return false
      return data.some(isJobActive) ? 2000 : false
    },
  })

  useEffect(() => {
    const jobs = query.data
    if (!jobs) return
    const nextActive = new Set<number>()
    for (const job of jobs) {
      if (isJobActive(job)) {
        nextActive.add(job.id)
      }
    }

    let anyFinished = false
    for (const prevId of prevActiveIdsRef.current) {
      if (!nextActive.has(prevId)) {
        anyFinished = true
        break
      }
    }
    prevActiveIdsRef.current = nextActive

    if (anyFinished) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.indexStats })
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodeAll })
      void queryClient.invalidateQueries({ queryKey: queryKeys.podcasts })
    }
  }, [query.data, queryClient])

  return query
}

export function useConversations() {
  return useQuery({
    queryKey: queryKeys.conversations,
    queryFn: getConversations,
  })
}

export function useConversation(id: number | null) {
  return useQuery({
    queryKey: queryKeys.conversation(id ?? 0),
    queryFn: () => getConversation(id!),
    enabled: id !== null && Number.isFinite(id) && id > 0,
  })
}

// --- Mutations -------------------------------------------------------------

export function useAddPodcast() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rssUrl: string) => createPodcast(rssUrl),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.podcasts })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.indexStats })
      void qc.invalidateQueries({ queryKey: ['discoverSearch'] })
      void qc.invalidateQueries({ queryKey: ['discoverTop'] })
    },
  })
}

export function useRefreshPodcast() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => refreshPodcast(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.podcasts })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.indexStats })
    },
  })
}

export function useDeletePodcast() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, deleteFiles = true }: { id: number; deleteFiles?: boolean }) =>
      deletePodcast(id, deleteFiles),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.podcasts })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodeAll })
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.indexStats })
    },
  })
}

export function useEstimateEpisodes() {
  return useMutation({
    mutationFn: (sel: SelectionRequest) => estimateEpisodes(sel),
  })
}

export function useProcessEpisodes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sel: SelectionRequest) => processEpisodes(sel),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodeAll })
    },
  })
}

export function useSummarizeEpisode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, force = false }: { id: number; force?: boolean }) =>
      summarizeEpisode(id, force),
    onSuccess: (_job, vars) => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episode(vars.id) })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
    },
  })
}

export function useReindexEpisode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reindexEpisode(id),
    onSuccess: (_job, id) => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episode(id) })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
    },
  })
}

export function useDeleteEpisodeData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteEpisodeData(id),
    onSuccess: (_void, id) => {
      void qc.invalidateQueries({ queryKey: queryKeys.episode(id) })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.podcasts })
      void qc.invalidateQueries({ queryKey: queryKeys.indexStats })
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
    },
  })
}

export function useRebuildIndex() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => rebuildIndex(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.indexStats })
    },
  })
}

export function useCancelJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => cancelJob(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodeAll })
    },
  })
}

/** Re-run the transcript health check for an episode. */
export function useCheckEpisode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => checkEpisode(id),
    onSuccess: (_d, id) => {
      void qc.invalidateQueries({ queryKey: queryKeys.episode(id) })
    },
  })
}

/** Books, polling every 2 s while any is being written. */
export function useBooks() {
  return useQuery({
    queryKey: queryKeys.books,
    queryFn: getBooks,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((b) => b.status === 'queued' || b.status === 'writing')
        ? 2000
        : false,
  })
}

export function useEstimateBook() {
  return useMutation({ mutationFn: (episodeId: number) => estimateBook(episodeId) })
}

export function useCreateBook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ episodeId, narrator }: { episodeId: number; narrator: string | null }) =>
      createBook(episodeId, narrator),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.books })
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
    },
  })
}

export function useReshuffleBook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reshuffleBook(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.books }),
  })
}

export function useDeleteBook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteBook(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.books }),
  })
}

export function useDeleteJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteJob(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.jobsAll }),
  })
}

export function useClearFinishedJobs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => clearFinishedJobs(),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.jobsAll }),
  })
}

export function useDiscoverGenres() {
  return useQuery({
    queryKey: queryKeys.discoverGenres,
    queryFn: getDiscoverGenres,
    staleTime: Infinity,
  })
}

/** Directory search by name; disabled until there is a query. */
export function useDirectorySearch(q: string) {
  const term = q.trim()
  return useQuery({
    queryKey: queryKeys.discoverSearch(term),
    queryFn: () => searchDirectory(term),
    enabled: term.length >= 2,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  })
}

export function useTopPodcasts(genreId: number | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.discoverTop(genreId),
    queryFn: () => getTopPodcasts(genreId),
    enabled,
    staleTime: 30 * 60_000,
  })
}

export function useRetryJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => retryJob(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.jobsAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodesAll })
      void qc.invalidateQueries({ queryKey: queryKeys.episodeAll })
    },
  })
}

export function usePatchConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ConversationPatch }) =>
      patchConversation(id, patch),
    onSuccess: (_conv, vars) => {
      void qc.invalidateQueries({ queryKey: queryKeys.conversations })
      void qc.invalidateQueries({ queryKey: queryKeys.conversation(vars.id) })
    },
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteConversation(id),
    onSuccess: (_void, id) => {
      void qc.invalidateQueries({ queryKey: queryKeys.conversations })
      qc.removeQueries({ queryKey: queryKeys.conversation(id) })
    },
  })
}
