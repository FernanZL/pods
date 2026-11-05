import { Link } from 'react-router-dom'
import { useEpisodes } from '../api/hooks'
import type { Episode, IndexStats } from '../api/types'
import { fmtDate, fmtDuration, fmtEpNumber, fmtNumber } from '../utils/format'
import { buildNamesColorMap, getSpeakerColor } from '../utils/speakers'
import { Skeleton } from './Spinner'
import './LibraryBrief.css'

interface LibraryBriefProps {
  stats: IndexStats | undefined
  onAskAbout: (episode: Episode) => void
}

/**
 * The new-chat apparatus: what the library holds, set as a short reference list of the
 * most recently indexed episodes, each one a door to a scoped question.
 */
export function LibraryBrief({ stats, onAskAbout }: LibraryBriefProps) {
  const recent = useEpisodes({ status: 'indexed', limit: 6 })
  const items = recent.data?.items ?? []

  return (
    <section className="library-brief" aria-labelledby="library-brief-heading">
      <h1 className="library-brief-heading">Ask across your indexed transcripts</h1>
      <p className="library-brief-sub">
        Every answer cites the exact episode, speaker, and timestamp. Ask about everything, or
        start from one episode below.
      </p>

      <div className="library-brief-list-head">
        <h2 id="library-brief-heading" className="library-brief-list-title">
          Recently indexed
        </h2>
        {stats ? (
          <span className="library-brief-count">
            {fmtNumber(stats.episodes_indexed)} of {fmtNumber(stats.episodes_total)} episodes in
            the index
          </span>
        ) : null}
      </div>

      {recent.isLoading ? (
        <div className="library-brief-skeletons">
          <Skeleton width="100%" height="44px" />
          <Skeleton width="100%" height="44px" />
          <Skeleton width="100%" height="44px" />
        </div>
      ) : (
        <ol className="library-brief-list">
          {items.map((ep) => {
            const names = Object.values(ep.speakers)
            const colors = buildNamesColorMap(names)
            return (
              <li key={ep.id} className="library-brief-item">
                <span className="library-brief-ep">{fmtEpNumber(ep.number)}</span>
                <div className="library-brief-body">
                  <Link to={`/episodes/${ep.id}`} className="library-brief-title" title={ep.title}>
                    {ep.title}
                  </Link>
                  <span className="library-brief-meta">
                    {names.slice(0, 3).map((name) => (
                      <span key={name} className="library-brief-speaker">
                        <span
                          className="library-brief-dot"
                          style={{ backgroundColor: getSpeakerColor(name, colors) }}
                          aria-hidden="true"
                        />
                        {name}
                      </span>
                    ))}
                    <span>{fmtDuration(ep.duration_seconds)}</span>
                    <span>{fmtNumber(ep.passage_count)} passages</span>
                    {ep.published ? <span>{fmtDate(ep.published)}</span> : null}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-sm library-brief-ask"
                  onClick={() => onAskAbout(ep)}
                  aria-label={`Ask about ${fmtEpNumber(ep.number)} ${ep.title}`}
                >
                  Ask about this
                </button>
              </li>
            )
          })}
        </ol>
      )}

      <Link to="/library" className="library-brief-more">
        Browse the full library
      </Link>
    </section>
  )
}
