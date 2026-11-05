import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  useCitedEpisodes,
  useConversations,
  useEpisodes,
  useIndexStats,
} from '../api/hooks'
import type { EpisodeDetail } from '../api/types'
import { IconSearch } from '../components/Icons'
import { fmtEpNumber, fmtHours, fmtNumber, fmtRelativeDate } from '../utils/format'
import './HomePage.css'

const TAPE_ROWS = 11

interface Turn {
  speaker: number // 0..3 speaker colour slot
  from: number // 0..1 position in the episode
  to: number
}

/** One indexed episode as a row of speaker turns, each as wide as its exact duration. */
function turnsFromEpisode(ep: EpisodeDetail): Turn[] {
  const segs = ep.segments
  if (segs.length === 0) return []
  const total = segs[segs.length - 1]!.end || 1
  const order = new Map<string, number>()
  return segs.map((s) => {
    if (!order.has(s.speaker)) order.set(s.speaker, order.size)
    return { speaker: order.get(s.speaker)! % 4, from: s.start / total, to: s.end / total }
  })
}

/** Deterministic stand-in rows (a conversation-like rhythm) until the library has episodes. */
function syntheticTurns(row: number): Turn[] {
  let seed = (row + 1) * 9301
  const rand = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  const turns: Turn[] = []
  let t = 0
  let speaker = 0
  while (t < 1) {
    const len = 0.006 + rand() * (speaker === 0 ? 0.03 : 0.06)
    turns.push({ speaker, from: t, to: Math.min(1, t + len) })
    t += len + 0.002
    speaker = rand() < 0.82 ? (speaker === 0 ? 1 : 0) : 2 + Math.floor(rand() * 2)
  }
  return turns
}

function TapeRow({ turns, index }: { turns: Turn[]; index: number }) {
  // Two identical copies side by side so the drift loops seamlessly.
  const blocks = turns.map((t, i) => (
    <rect
      key={i}
      x={t.from * 1000}
      y={0}
      width={Math.max(0.6, (t.to - t.from) * 1000 - 0.8)}
      height={10}
      rx={1}
      className={`home-tape-turn home-tape-turn--s${t.speaker}`}
    />
  ))
  return (
    <div
      className="home-tape-row"
      style={{
        animationDuration: `${140 + ((index * 37) % 90)}s`,
        animationDirection: index % 2 ? 'reverse' : 'normal',
        opacity: 0.38 + ((index * 23) % 50) / 100,
      }}
    >
      {[0, 1].map((copy) => (
        <svg
          key={copy}
          className="home-tape-svg"
          viewBox="0 0 1000 10"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {blocks}
        </svg>
      ))}
    </div>
  )
}

export function HomePage() {
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const { data: stats } = useIndexStats()
  const { data: conversations } = useConversations()
  const indexed = useEpisodes({ status: 'indexed', limit: TAPE_ROWS })
  const recentEpisodes = useMemo(() => indexed.data?.items ?? [], [indexed.data])
  const details = useCitedEpisodes(recentEpisodes.map((e) => e.id))

  const rows = useMemo(() => {
    const real = recentEpisodes
      .map((e) => details.get(e.id))
      .filter((d): d is EpisodeDetail => Boolean(d && d.segments.length))
      .map(turnsFromEpisode)
    return Array.from({ length: TAPE_ROWS }, (_, i) =>
      real.length > 0 ? real[i % real.length]! : syntheticTurns(i),
    )
  }, [recentEpisodes, details])

  const hasLibrary = Boolean(stats && stats.episodes_indexed > 0)

  const ask = (e: FormEvent) => {
    e.preventDefault()
    const q = question.trim()
    navigate(q ? `/chat?q=${encodeURIComponent(q)}` : '/chat')
  }

  return (
    <main id="main-content" className="home">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-tapes" aria-hidden="true">
          {rows.map((turns, i) => (
            <TapeRow key={i} turns={turns} index={i} />
          ))}
        </div>

        <div className="home-hero-inner">
          <h1 id="home-title" className="home-title">
            Ask your podcasts.
          </h1>
          <p className="home-sub">
            {hasLibrary && stats
              ? `${fmtNumber(stats.episodes_indexed)} episodes and ${fmtHours(stats.hours_indexed)} hours of conversation, transcribed by voice and ready to cite.`
              : 'Collect episodes once, transcribed by voice, and ask them anything with answers that cite who said it and when.'}
          </p>

          {hasLibrary ? (
            <form className="home-ask" onSubmit={ask}>
              <span className="home-ask-icon" aria-hidden="true">
                <IconSearch size={18} />
              </span>
              <input
                className="home-ask-input"
                aria-label="Ask a question about your podcast library"
                placeholder="What did they say about morning light?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                autoFocus
              />
              <button type="submit" className="home-ask-btn">
                Ask
              </button>
            </form>
          ) : (
            <div className="home-start">
              <Link to="/library?tab=browse" className="home-ask-btn home-start-btn">
                Find your first podcast
              </Link>
            </div>
          )}
        </div>
      </section>

      <section className="home-below" aria-label="Pick up where you left off">
        <div className="home-col">
          <h2 className="home-col-title">Continue</h2>
          {conversations && conversations.length > 0 ? (
            <ul className="home-list">
              {conversations.slice(0, 4).map((c) => (
                <li key={c.id}>
                  <Link to={`/chat/${c.id}`} className="home-list-link">
                    <span className="home-list-main">{c.title}</span>
                    <span className="home-list-meta">{fmtRelativeDate(c.updated_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="home-empty">Your conversations will show up here.</p>
          )}
        </div>

        <div className="home-col">
          <h2 className="home-col-title">Recently indexed</h2>
          {recentEpisodes.length > 0 ? (
            <ul className="home-list">
              {recentEpisodes.slice(0, 4).map((ep) => (
                <li key={ep.id}>
                  <Link to={`/episodes/${ep.id}`} className="home-list-link">
                    <span className="home-list-main">
                      <span className="home-list-ep">{fmtEpNumber(ep.number)}</span> {ep.title}
                    </span>
                    <span className="home-list-meta">{ep.podcast_title}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="home-empty">Nothing indexed yet.</p>
          )}
        </div>

        <div className="home-col">
          <h2 className="home-col-title">Grow the library</h2>
          <ul className="home-list">
            <li>
              <Link to="/library?tab=browse" className="home-list-link">
                <span className="home-list-main">Browse top podcasts</span>
                <span className="home-list-meta">Search by name</span>
              </Link>
            </li>
            <li>
              <Link to="/library" className="home-list-link">
                <span className="home-list-main">Process more episodes</span>
                <span className="home-list-meta">
                  {stats ? `${fmtNumber(stats.episodes_total - stats.episodes_indexed)} waiting` : ''}
                </span>
              </Link>
            </li>
            <li>
              <Link to="/jobs" className="home-list-link">
                <span className="home-list-main">Check jobs</span>
                <span className="home-list-meta">Progress and history</span>
              </Link>
            </li>
          </ul>
        </div>
      </section>
    </main>
  )
}
