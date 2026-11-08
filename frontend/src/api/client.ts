import type {
  Book,
  BookEstimate,
  BookQuote,
  BookForm,
  BookTense,
  Episode,
  TranscriptCheck,
  DiscoverGenre,
  DiscoverPodcast,
  EpisodeCitationRef,
  AppConfig,
  Conversation,
  ConversationDetail,
  ConversationPatch,
  CostEstimate,
  EpisodeDetail,
  EpisodeList,
  EpisodeStatus,
  IndexStats,
  Job,
  Podcast,
  SelectionRequest,
} from './types'

const API_BASE = '/api'

/** Structured error thrown by API calls for non-2xx HTTP responses. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function extractErrorDetail(res: Response): Promise<string> {
  const text = await res.text()
  if (text) {
    try {
      const parsed: unknown = JSON.parse(text)
      if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
        const rawDetail = (parsed as { detail: unknown }).detail
        if (typeof rawDetail === 'string' && rawDetail.trim()) {
          return rawDetail
        }
        if (Array.isArray(rawDetail)) {
          const messages = rawDetail
            .map((item) => {
              if (item && typeof item === 'object' && 'msg' in item) {
                return String((item as { msg: unknown }).msg)
              }
              return typeof item === 'string' ? item : ''
            })
            .filter(Boolean)
          if (messages.length > 0) {
            return messages.join('; ')
          }
        }
      }
    } catch {
      if (text.length < 240) {
        return text.trim()
      }
    }
  }
  return res.statusText || `Request failed (${res.status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  })

  if (!res.ok) {
    const detail = await extractErrorDetail(res)
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return (await res.json()) as T
}

export interface EpisodesFilter {
  podcast_id?: number | null
  q?: string
  search_description?: boolean
  status?: EpisodeStatus | ''
  /** Only episodes already in the library (worked on, or with a job on its way). */
  collected?: boolean
  limit?: number
  offset?: number
}

export interface JobsFilter {
  status?: string
  limit?: number
}

/** GET /api/health */
export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>('/health')
}

/** GET /api/config */
export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>('/config')
}

/** GET /api/podcasts */
export function getPodcasts(): Promise<Podcast[]> {
  return request<Podcast[]>('/podcasts')
}

/** POST /api/podcasts */
export function createPodcast(rssUrl: string): Promise<Podcast> {
  return request<Podcast>('/podcasts', {
    method: 'POST',
    body: JSON.stringify({ rss_url: rssUrl }),
  })
}

/** POST /api/podcasts/{id}/refresh */
export function refreshPodcast(id: number): Promise<Podcast> {
  return request<Podcast>(`/podcasts/${encodeURIComponent(String(id))}/refresh`, {
    method: 'POST',
  })
}

/** DELETE /api/podcasts/{id} */
export function deletePodcast(id: number, deleteFiles = true): Promise<void> {
  const qs = new URLSearchParams({ delete_files: String(deleteFiles) }).toString()
  return request<void>(`/podcasts/${encodeURIComponent(String(id))}?${qs}`, {
    method: 'DELETE',
  })
}

/** GET /api/episodes */
export function getEpisodes(filter?: EpisodesFilter): Promise<EpisodeList> {
  const params = new URLSearchParams()
  if (filter) {
    if (filter.podcast_id !== undefined && filter.podcast_id !== null) {
      params.set('podcast_id', String(filter.podcast_id))
    }
    if (filter.q && filter.q.trim()) {
      params.set('q', filter.q.trim())
    }
    if (filter.search_description) {
      params.set('search_description', 'true')
    }
    if (filter.status) {
      params.set('status', filter.status)
    }
    if (filter.collected) {
      params.set('collected', 'true')
    }
    if (filter.limit !== undefined) {
      params.set('limit', String(filter.limit))
    }
    if (filter.offset !== undefined) {
      params.set('offset', String(filter.offset))
    }
  }
  const qs = params.toString()
  return request<EpisodeList>(qs ? `/episodes?${qs}` : '/episodes')
}

export interface UploadEpisodeInput {
  file: File
  title?: string
  show?: string
  description?: string
}

/**
 * POST /api/episodes/upload (multipart). Uses XHR rather than fetch so the caller can
 * show upload progress for large audio files. `onProgress` gets 0..1.
 */
export function uploadEpisode(
  input: UploadEpisodeInput,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<Episode> {
  const form = new FormData()
  form.append('file', input.file)
  if (input.title?.trim()) form.append('title', input.title.trim())
  if (input.show?.trim()) form.append('show', input.show.trim())
  if (input.description?.trim()) form.append('description', input.description.trim())

  return new Promise<Episode>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/episodes/upload`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Episode)
        } catch {
          reject(new ApiError(xhr.status, 'The server sent an unreadable response.'))
        }
        return
      }
      const res = new Response(xhr.responseText || null, {
        status: xhr.status,
        statusText: xhr.statusText,
      })
      void extractErrorDetail(res).then((detail) => reject(new ApiError(xhr.status, detail)))
    }
    xhr.onerror = () => reject(new ApiError(0, 'The upload could not reach the server.'))
    xhr.onabort = () => reject(new ApiError(0, 'Upload cancelled.'))
    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

/** GET /api/episodes/{id} */
export function getEpisode(id: number): Promise<EpisodeDetail> {
  return request<EpisodeDetail>(`/episodes/${encodeURIComponent(String(id))}`)
}

export function getEpisodeCitations(id: number): Promise<EpisodeCitationRef[]> {
  return request<EpisodeCitationRef[]>(`/episodes/${encodeURIComponent(String(id))}/citations`)
}

/** URL for streaming local audio with Range support (<audio src=...>). */
export function episodeAudioUrl(id: number): string {
  return `${API_BASE}/episodes/${encodeURIComponent(String(id))}/audio`
}

/** POST /api/episodes/estimate */
export function estimateEpisodes(sel: SelectionRequest): Promise<CostEstimate> {
  return request<CostEstimate>('/episodes/estimate', {
    method: 'POST',
    body: JSON.stringify(sel),
  })
}

/** POST /api/episodes/process */
export function processEpisodes(sel: SelectionRequest): Promise<Job[]> {
  return request<Job[]>('/episodes/process', {
    method: 'POST',
    body: JSON.stringify(sel),
  })
}

/** POST /api/episodes/{id}/summarize */
export function summarizeEpisode(id: number, force = false): Promise<Job> {
  const qs = force ? '?force=true' : ''
  return request<Job>(`/episodes/${encodeURIComponent(String(id))}/summarize${qs}`, {
    method: 'POST',
  })
}

/** POST /api/episodes/{id}/reindex */
export function reindexEpisode(id: number): Promise<Job> {
  return request<Job>(`/episodes/${encodeURIComponent(String(id))}/reindex`, {
    method: 'POST',
  })
}

/** DELETE /api/episodes/{id}/data */
export function deleteEpisodeData(id: number): Promise<void> {
  return request<void>(`/episodes/${encodeURIComponent(String(id))}/data`, {
    method: 'DELETE',
  })
}

/** GET /api/jobs */
export function getJobs(filter?: JobsFilter): Promise<Job[]> {
  const params = new URLSearchParams()
  if (filter?.status) {
    params.set('status', filter.status)
  }
  if (filter?.limit !== undefined) {
    params.set('limit', String(filter.limit))
  }
  const qs = params.toString()
  return request<Job[]>(qs ? `/jobs?${qs}` : '/jobs')
}

/** GET /api/jobs/{id} */
export function getJob(id: number): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(String(id))}`)
}

/** POST /api/jobs/{id}/cancel */
export function cancelJob(id: number): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(String(id))}/cancel`, {
    method: 'POST',
  })
}

/** POST /api/jobs/{id}/retry */
/** Delete one finished job record (history only). */
export function deleteJob(id: number): Promise<void> {
  return request<void>(`/jobs/${encodeURIComponent(String(id))}`, { method: 'DELETE' })
}

/** Delete every finished (done / failed / cancelled) job record. */
export function clearFinishedJobs(): Promise<{ deleted: number }> {
  return request<{ deleted: number }>('/jobs', { method: 'DELETE' })
}

export function checkEpisode(id: number): Promise<TranscriptCheck> {
  return request<TranscriptCheck>(`/episodes/${id}/check`, { method: 'POST' })
}

// --- Books ---
export function getBooks(): Promise<Book[]> {
  return request<Book[]>('/books')
}

export function estimateBook(episodeId: number): Promise<BookEstimate> {
  return request<BookEstimate>('/books/estimate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ episode_id: episodeId }),
  })
}

export function createBook(
  episodeId: number,
  narrator: string | null = null,
  tense: BookTense = 'past',
  form: BookForm = 'retelling',
): Promise<Book> {
  return request<Book>('/books', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ episode_id: episodeId, narrator, tense, form }),
  })
}

export function reshuffleBook(id: number): Promise<Book> {
  return request<Book>(`/books/${id}/reshuffle`, { method: 'POST' })
}

export function deleteBook(id: number): Promise<void> {
  return request<void>(`/books/${id}`, { method: 'DELETE' })
}

/** PDF URL; `download` sets Content-Disposition: attachment. */
export function bookPdfUrl(id: number, download = false): string {
  return `${API_BASE}/books/${id}/pdf${download ? '?download=true' : ''}`
}

/** Cover thumbnail; `v` busts the cache after a reshuffle. */
/** GET /api/books/quote (null when no finished book has a pull quote yet) */
export function getBookQuote(): Promise<BookQuote | null> {
  return request<BookQuote | null>('/books/quote')
}

/** The show's artwork as a duotone poster; 404 when it has none. */
export function podcastPosterUrl(id: number): string {
  return `${API_BASE}/podcasts/${encodeURIComponent(String(id))}/poster.png`
}

export function bookCoverUrl(id: number, v: string | number): string {
  return `${API_BASE}/books/${id}/cover.png?v=${encodeURIComponent(String(v))}`
}

export function getDiscoverGenres(): Promise<DiscoverGenre[]> {
  return request<DiscoverGenre[]>('/discover/genres')
}

export function searchDirectory(q: string): Promise<DiscoverPodcast[]> {
  return request<DiscoverPodcast[]>(`/discover/search?q=${encodeURIComponent(q)}&limit=24`)
}

export function getTopPodcasts(genreId: number | null): Promise<DiscoverPodcast[]> {
  const genre = genreId ? `genre_id=${genreId}&` : ''
  return request<DiscoverPodcast[]>(`/discover/top?${genre}limit=24`)
}

export function retryJob(id: number): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(String(id))}/retry`, {
    method: 'POST',
  })
}

/** GET /api/index/stats */
export function getIndexStats(): Promise<IndexStats> {
  return request<IndexStats>('/index/stats')
}

/** POST /api/index/rebuild */
export function rebuildIndex(): Promise<Job> {
  return request<Job>('/index/rebuild', {
    method: 'POST',
  })
}

/** GET /api/conversations */
export function getConversations(): Promise<Conversation[]> {
  return request<Conversation[]>('/conversations')
}

/** GET /api/conversations/{id} */
export function getConversation(id: number): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(String(id))}`)
}

/** PATCH /api/conversations/{id} */
export function patchConversation(id: number, patch: ConversationPatch): Promise<Conversation> {
  return request<Conversation>(`/conversations/${encodeURIComponent(String(id))}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

/** DELETE /api/conversations/{id} */
export function deleteConversation(id: number): Promise<void> {
  return request<void>(`/conversations/${encodeURIComponent(String(id))}`, {
    method: 'DELETE',
  })
}
