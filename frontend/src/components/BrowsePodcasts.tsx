import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useAddPodcast, useDirectorySearch, useDiscoverGenres, useTopPodcasts } from '../api/hooks'
import type { DiscoverPodcast, Podcast } from '../api/types'
import { fmtNumber } from '../utils/format'
import { ErrorBanner } from './ErrorBanner'
import { IconCheck, IconPlus, IconSearch } from './Icons'
import { Skeleton, Spinner } from './Spinner'
import './BrowsePodcasts.css'

interface BrowsePodcastsProps {
  /** Called after a podcast is added (or when "In library" is chosen). */
  onOpenInLibrary: (podcastId: number) => void
  onAdded: (podcast: Podcast) => void
}

/**
 * Find podcasts without knowing their feed: search the Apple Podcasts directory by
 * name, or browse top charts by genre, and add one in a click. Pasting an RSS URL
 * remains as a fallback for shows that are not listed.
 */
export function BrowsePodcasts({ onOpenInLibrary, onAdded }: BrowsePodcastsProps) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [genreId, setGenreId] = useState<number | null>(null)
  const [addingId, setAddingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rssInput, setRssInput] = useState('')

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 350)
    return () => window.clearTimeout(t)
  }, [query])

  const searching = debounced.length >= 2
  const genres = useDiscoverGenres()
  const search = useDirectorySearch(debounced)
  const top = useTopPodcasts(genreId, !searching)
  const active = searching ? search : top
  const results = active.data ?? []
  const addPodcast = useAddPodcast()

  const add = (rssUrl: string, itunesId: number | null) => {
    setError(null)
    setAddingId(itunesId)
    addPodcast.mutate(rssUrl, {
      onSuccess: (created) => {
        setRssInput('')
        onAdded(created)
      },
      onError: (err) =>
        setError(err instanceof ApiError ? err.detail : 'Could not add this podcast.'),
      onSettled: () => setAddingId(null),
    })
  }

  const handleRssSubmit = (e: FormEvent) => {
    e.preventDefault()
    const url = rssInput.trim()
    if (url && !addPodcast.isPending) add(url, null)
  }

  const genreName = genres.data?.find((g) => g.id === genreId)?.name

  return (
    <section className="browse" aria-labelledby="browse-heading">
      <h2 id="browse-heading" className="sr-only">
        Browse podcasts
      </h2>

      <div className="browse-search">
        <span className="browse-search-icon" aria-hidden="true">
          <IconSearch size={16} />
        </span>
        <input
          type="search"
          className="input browse-search-input"
          placeholder="Search podcasts by name or host, for example Huberman"
          aria-label="Search podcasts by name or host"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>

      {!searching ? (
        <div className="browse-genres" role="group" aria-label="Top charts by genre">
          <button
            type="button"
            className={`browse-genre ${genreId === null ? 'browse-genre--on' : ''}`.trim()}
            aria-pressed={genreId === null}
            onClick={() => setGenreId(null)}
          >
            All
          </button>
          {(genres.data ?? []).map((g) => (
            <button
              key={g.id}
              type="button"
              className={`browse-genre ${genreId === g.id ? 'browse-genre--on' : ''}`.trim()}
              aria-pressed={genreId === g.id}
              onClick={() => setGenreId(g.id)}
            >
              {g.name}
            </button>
          ))}
        </div>
      ) : null}

      <div className="browse-results-head">
        <h3 className="browse-results-title">
          {searching
            ? `Results for "${debounced}"`
            : `Top podcasts${genreName ? ` in ${genreName}` : ''}`}
        </h3>
        <span className="browse-source">Apple Podcasts directory</span>
      </div>

      {error ? (
        <ErrorBanner message="Could not add podcast." recovery={error} onDismiss={() => setError(null)} />
      ) : null}

      {active.error ? (
        <ErrorBanner
          message="The podcast directory could not be reached."
          recovery={
            active.error instanceof ApiError
              ? `${active.error.detail} You can still add a show by its RSS feed URL below.`
              : undefined
          }
          onRetry={() => void active.refetch()}
        />
      ) : active.isLoading ? (
        <div className="browse-grid">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} height="88px" />
          ))}
        </div>
      ) : results.length === 0 ? (
        <p className="browse-empty">
          {searching
            ? 'No podcasts match that name. Try the host, or paste the RSS feed URL below.'
            : 'No chart entries right now.'}
        </p>
      ) : (
        <ul className="browse-grid">
          {results.map((p) => (
            <ResultCard
              key={p.itunes_id}
              podcast={p}
              adding={addingId === p.itunes_id && addPodcast.isPending}
              onAdd={() => p.feed_url && add(p.feed_url, p.itunes_id)}
              onOpen={() => p.podcast_id && onOpenInLibrary(p.podcast_id)}
            />
          ))}
        </ul>
      )}

      <form className="browse-rss" onSubmit={handleRssSubmit}>
        <label htmlFor="browse-rss-url" className="browse-rss-label">
          Have an RSS feed URL instead?
        </label>
        <div className="browse-rss-row">
          <input
            id="browse-rss-url"
            type="url"
            className="input input-sm browse-rss-input"
            placeholder="https://feeds.megaphone.fm/..."
            value={rssInput}
            onChange={(e) => setRssInput(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-sm"
            disabled={!rssInput.trim() || addPodcast.isPending}
          >
            {addPodcast.isPending && addingId === null ? (
              <Spinner size={12} label="Adding feed" />
            ) : null}
            <span>Add feed</span>
          </button>
        </div>
      </form>
    </section>
  )
}

interface ResultCardProps {
  podcast: DiscoverPodcast
  adding: boolean
  onAdd: () => void
  onOpen: () => void
}

function ResultCard({ podcast, adding, onAdd, onOpen }: ResultCardProps) {
  const meta = [podcast.genre, podcast.episode_count ? `${fmtNumber(podcast.episode_count)} episodes` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <li className="browse-card">
      {podcast.artwork_url ? (
        <img
          className="browse-art"
          src={podcast.artwork_url}
          alt=""
          width={64}
          height={64}
          loading="lazy"
        />
      ) : (
        <span className="browse-art browse-art--empty" aria-hidden="true" />
      )}
      <div className="browse-card-body">
        <span className="browse-card-title" title={podcast.title}>
          {podcast.title}
        </span>
        <span className="browse-card-author">{podcast.author}</span>
        {meta ? <span className="browse-card-meta">{meta}</span> : null}
      </div>
      <div className="browse-card-action">
        {podcast.podcast_id ? (
          <button type="button" className="btn btn-sm btn-ghost browse-in-library" onClick={onOpen}>
            <IconCheck size={12} />
            <span>In library</span>
          </button>
        ) : podcast.feed_url ? (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={onAdd}
            disabled={adding}
            aria-label={`Add ${podcast.title} to your library`}
          >
            {adding ? <Spinner size={12} label="Adding" /> : <IconPlus size={12} />}
            <span>Add</span>
          </button>
        ) : (
          <span className="browse-no-feed" title="Apple does not list a public RSS feed for this show">
            No public feed
          </span>
        )}
      </div>
    </li>
  )
}
