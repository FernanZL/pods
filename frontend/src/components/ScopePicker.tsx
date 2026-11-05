import { useEffect, useId, useRef, useState } from 'react'
import { useEpisodes, usePodcasts } from '../api/hooks'
import type { Scope } from '../api/types'
import { fmtEpNumber } from '../utils/format'
import { IconChevronDown, IconSearch } from './Icons'
import './ScopePicker.css'

type Mode = 'all' | 'podcasts' | 'episodes'

interface ScopePickerProps {
  scope: Scope
  onChange: (next: Scope) => void
  disabled?: boolean
}

function modeOf(scope: Scope): Mode {
  if (scope.episode_ids?.length) return 'episodes'
  if (scope.podcast_ids?.length) return 'podcasts'
  return 'all'
}

/** Chooses what the chat searches: everything, whole podcasts, or chosen episodes. */
export function ScopePicker({ scope, onChange, disabled }: ScopePickerProps) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>(modeOf(scope))
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const popoverId = useId()

  const podcasts = usePodcasts()
  const episodes = useEpisodes({ q: debounced, status: 'indexed', limit: 50 })

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 300)
    return () => window.clearTimeout(t)
  }, [query])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const podcastIds = scope.podcast_ids ?? []
  const episodeIds = scope.episode_ids ?? []

  const label = (() => {
    const m = modeOf(scope)
    if (m === 'episodes') return `${episodeIds.length} episode${episodeIds.length === 1 ? '' : 's'}`
    if (m === 'podcasts') {
      if (podcastIds.length === 1) {
        return podcasts.data?.find((p) => p.id === podcastIds[0])?.title ?? '1 podcast'
      }
      return `${podcastIds.length} podcasts`
    }
    return 'All episodes'
  })()

  const toggle = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id]

  const pickMode = (next: Mode) => {
    setMode(next)
    if (next === 'all') onChange({ podcast_ids: null, episode_ids: null })
  }

  return (
    <div className="scope-picker" ref={rootRef}>
      <button
        type="button"
        className="scope-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={popoverId}
        disabled={disabled}
        title={disabled ? 'Index episodes in Library to choose a scope' : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="scope-trigger-prefix">Scope</span>
        <span className="scope-trigger-value">{label}</span>
        <IconChevronDown />
      </button>

      {open ? (
        <div className="scope-popover" id={popoverId} role="dialog" aria-label="Chat scope">
          <div className="scope-popover-head">
            <div className="scope-tabs" role="tablist" aria-label="Scope type">
              {(['all', 'podcasts', 'episodes'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={mode === m}
                  className={`scope-tab${mode === m ? ' scope-tab--on' : ''}`}
                  onClick={() => pickMode(m)}
                >
                  {m === 'all' ? 'All' : m === 'podcasts' ? 'Podcasts' : 'Episodes'}
                </button>
              ))}
            </div>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setOpen(false)}>
              Done
            </button>
          </div>

          {mode === 'all' ? (
            <div className="scope-panel">
              <p className="scope-hint">Answers draw on every indexed episode in your library.</p>
            </div>
          ) : null}

          {mode === 'podcasts' ? (
            <div className="scope-panel">
              <p className="scope-hint">Only search the podcasts you tick.</p>
              <ul className="scope-option-list">
                {(podcasts.data ?? []).map((p) => (
                  <li key={p.id}>
                    <label className="scope-option">
                      <input
                        type="checkbox"
                        checked={podcastIds.includes(p.id)}
                        onChange={() =>
                          onChange({ podcast_ids: toggle(podcastIds, p.id), episode_ids: null })
                        }
                      />
                      <span className="scope-option-main">{p.title}</span>
                      <span className="scope-option-meta">{p.indexed_count} indexed</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {mode === 'episodes' ? (
            <div className="scope-panel">
              <div className="scope-search-box">
                <span className="scope-search-icon">
                  <IconSearch />
                </span>
                <input
                  type="search"
                  className="input scope-search-input"
                  placeholder="Search indexed episodes"
                  aria-label="Search indexed episodes"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <ul className="scope-option-list">
                {(episodes.data?.items ?? []).map((ep) => (
                  <li key={ep.id}>
                    <label className="scope-option">
                      <input
                        type="checkbox"
                        checked={episodeIds.includes(ep.id)}
                        onChange={() =>
                          onChange({ podcast_ids: null, episode_ids: toggle(episodeIds, ep.id) })
                        }
                      />
                      <span className="scope-option-main">
                        <span className="scope-ep-num">{fmtEpNumber(ep.number)}</span> {ep.title}
                      </span>
                    </label>
                  </li>
                ))}
                {episodes.data && episodes.data.items.length === 0 ? (
                  <li className="scope-hint">No indexed episodes match.</li>
                ) : null}
              </ul>
              <div className="scope-panel-foot">
                <span>{episodeIds.length} selected</span>
                {episodeIds.length ? (
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={() => onChange({ podcast_ids: null, episode_ids: null })}
                  >
                    Clear
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
