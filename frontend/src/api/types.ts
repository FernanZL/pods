// CONTRACT FILE — mirrors backend/app/schemas.py. Do not edit without updating both.

export type Step = 'download' | 'transcribe' | 'index'
export type EpisodeStatus = 'new' | 'downloaded' | 'transcribed' | 'indexed'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export type JobKind = 'process' | 'summarize' | 'reindex' | 'rebuild_index' | 'book'
export type ISODate = string

export interface Prices {
  transcription_per_min: number
  embedding_per_mtok: number
  llm_input_per_mtok: number
  llm_output_per_mtok: number
}

export interface AppConfig {
  llm_provider: string
  llm_model: string
  transcriber: string
  transcription_model: string
  embedding_model: string
  fake_mode: boolean
  has_openai_key: boolean
  has_openrouter_key: boolean
  prices: Prices
}

export interface Podcast {
  id: number
  title: string
  rss_url: string
  description: string
  image_url: string | null
  episode_count: number
  indexed_count: number
  refreshed_at: ISODate | null
}

export interface Episode {
  id: number
  podcast_id: number
  podcast_title: string
  number: number
  title: string
  description: string
  published: ISODate | null
  duration_seconds: number | null
  status: EpisodeStatus
  has_summary: boolean
  speakers: Record<string, string>
  passage_count: number
  active_job_id: number | null
}

export interface EpisodeList {
  items: Episode[]
  total: number
}

export interface Segment {
  speaker: string
  start: number
  end: number
  text: string
}

export interface EpisodeDetail extends Episode {
  audio_url: string
  local_audio: boolean
  downloaded_at: ISODate | null
  transcribed_at: ISODate | null
  indexed_at: ISODate | null
  summarized_at: ISODate | null
  segments: Segment[]
  summary_markdown: string | null
}

export interface SelectionRequest {
  episode_ids?: number[] | null
  podcast_id?: number | null
  q?: string | null
  search_description?: boolean
  status?: EpisodeStatus | null
  steps?: Step[]
  force?: boolean
}

export interface CostEstimate {
  episode_count: number
  known_minutes: number
  unknown_duration_count: number
  transcription_usd: number
  embedding_usd: number
  llm_usd: number
  total_usd: number
  skipped_already_done: number
}

export interface Job {
  id: number
  kind: JobKind
  episode_id: number | null
  episode_title: string | null
  steps: Step[]
  status: JobStatus
  current_step: string | null
  progress: number
  message: string
  error: string | null
  created_at: ISODate
  started_at: ISODate | null
  finished_at: ISODate | null
}

export interface IndexStats {
  podcasts: number
  episodes_total: number
  episodes_indexed: number
  passages: number
  embedding_model: string
  hours_indexed: number
}

export interface Scope {
  podcast_ids?: number[] | null
  episode_ids?: number[] | null
}

export interface ChatRequest {
  conversation_id?: number | null
  message: string
  scope?: Scope
}

export interface Citation {
  n: number
  episode_id: number
  episode_number: number
  episode_title: string
  podcast_title: string
  speaker: string
  start: number
  end: number
  source: 'transcript' | 'summary'
  snippet: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  created_at: ISODate
}

export interface Conversation {
  id: number
  title: string
  scope: Scope
  created_at: ISODate
  updated_at: ISODate
  message_count: number
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface ConversationPatch {
  title?: string
  scope?: Scope
}

// --- POST /api/chat server-sent events ---------------------------------
export type ChatEvent =
  | { event: 'meta'; data: { conversation_id: number; user_message_id: number; query: string } }
  | { event: 'citations'; data: { citations: Citation[] } }
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: { assistant_message_id: number; citations: Citation[] } }
  | { event: 'error'; data: { detail: string } }

// GET /api/episodes/:id/citations — where saved answers cited this episode
export interface EpisodeCitationRef {
  conversation_id: number
  conversation_title: string
  message_id: number
  n: number
  start: number
  end: number
  speaker: string
  created_at: ISODate
}

// --- Discover (Apple Podcasts directory) ---------------------------------
export interface DiscoverPodcast {
  itunes_id: number
  title: string
  author: string
  feed_url: string | null
  artwork_url: string | null
  genre: string | null
  episode_count: number | null
  podcast_id: number | null // already in the library
}

export interface DiscoverGenre {
  id: number
  name: string
}

// --- Books -----------------------------------------------------------------
export type BookStatus = 'queued' | 'writing' | 'ready' | 'failed'

export interface Book {
  id: number
  episode_id: number
  episode_number: number
  episode_title: string
  podcast_title: string
  status: BookStatus
  job_id: number | null
  progress: number
  message: string
  title: string
  seed: number
  family: string
  art: string
  chapters: number
  words: number
  pages: number
  quotes: number
  rejected_quotes: number
  error: string | null
  created_at: ISODate
  updated_at: ISODate
}

export interface BookEstimate {
  episode_id: number
  transcript_words: number
  chapters: number
  target_words: number
  est_pages: number
  llm_usd: number
  model: string
}
