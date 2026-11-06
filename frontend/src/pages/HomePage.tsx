import '@fontsource/anton'
import '@fontsource-variable/archivo'
import '@fontsource/permanent-marker'
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { bookCoverUrl, bookPdfUrl, podcastPosterUrl } from '../api/client'
import {
  isJobActive,
  useBookQuote,
  useBooks,
  useCitedEpisodes,
  useConversations,
  useEpisodes,
  useIndexStats,
  useJobs,
  usePodcasts,
} from '../api/hooks'
import type { Book, Episode, EpisodeDetail, Podcast } from '../api/types'
import { fmtEpNumber, fmtNumber, fmtRelativeDate, fmtTime } from '../utils/format'
import './HomePage.css'

const CRATE_INDEXED = 6
const CRATE_SEALED = 4
const GROOVE_TURNS = 34

const FLIP_OUT_MS = 180 // the front sleeve tips back into the crate
const FLIP_IN_MS = 520 // the next one rises into place

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const plural = (n: number, one: string, many = `${one}s`) =>
  `${fmtNumber(n)} ${n === 1 ? one : many}`

// ------------------------------------------------------------------ the groove

interface Voice {
  label: string
  name: string
  slot: number // 0..3 colour slot, -1 for minor voices
}

/** Main voices (at least 5% of the talk) in order of first appearance. */
function voicesOf(ep: EpisodeDetail): Voice[] {
  const talk = new Map<string, number>()
  let total = 0
  for (const s of ep.segments) {
    const d = Math.max(0, s.end - s.start)
    talk.set(s.speaker, (talk.get(s.speaker) ?? 0) + d)
    total += d
  }
  const voices: Voice[] = []
  for (const s of ep.segments) {
    if (voices.some((v) => v.label === s.speaker)) continue
    const main = (talk.get(s.speaker) ?? 0) / (total || 1) >= 0.05
    const slot = main ? voices.filter((v) => v.slot >= 0).length : -1
    voices.push({ label: s.speaker, name: ep.speakers[s.speaker] ?? s.speaker, slot: slot > 3 ? -1 : slot })
  }
  return voices
}

/** The whole conversation as one record groove: a spiral, each turn in its speaker's colour. */
function Groove({ ep, voices }: { ep: EpisodeDetail; voices: Voice[] }) {
  const lines = useMemo(() => {
    const segs = ep.segments
    const total = segs.length ? segs[segs.length - 1]!.end || 1 : 1
    const slotOf = new Map(voices.map((v) => [v.label, v.slot]))
    const rOut = 168
    const rIn = 58
    return segs.map((s) => {
      const a0 = s.start / total
      const a1 = s.end / total
      const steps = Math.max(2, Math.round((a1 - a0) * GROOVE_TURNS * 90))
      const pts: string[] = []
      for (let k = 0; k <= steps; k++) {
        const f = a0 + ((a1 - a0) * k) / steps
        const r = rOut - (rOut - rIn) * f
        const ang = f * GROOVE_TURNS * 2 * Math.PI - Math.PI / 2
        pts.push(`${(r * Math.cos(ang)).toFixed(1)},${(r * Math.sin(ang)).toFixed(1)}`)
      }
      return { points: pts.join(' '), slot: slotOf.get(s.speaker) ?? -1 }
    })
  }, [ep, voices])

  return (
    <svg className="home-groove" viewBox="-200 -262 400 400" aria-hidden="true">
      <circle r="174" className="home-groove-vinyl" />
      {lines.map((l, i) => (
        <polyline key={i} points={l.points} className={`home-groove-turn home-groove-turn--s${l.slot}`} />
      ))}
      <circle r="50" className="home-groove-label" />
      <circle r="4" className="home-groove-hole" />
    </svg>
  )
}

// ------------------------------------------------------------------ the crate

type CrateItem =
  | { kind: 'record'; ep: Episode; detail: EpisodeDetail | undefined }
  | { kind: 'sealed'; ep: Episode }

function sleeveTitle(ep: Episode) {
  return `${fmtEpNumber(ep.number)} · ${ep.title}`
}

function FrontSleeve({ item }: { item: CrateItem }) {
  const { ep } = item
  if (item.kind === 'sealed') {
    return (
      <Link to={`/episodes/${ep.id}`} className="home-sleeve home-sleeve--front home-sleeve--sealed">
        <span className="home-sleeve-show">{ep.podcast_title}</span>
        <span className="home-sleeve-num">{ep.number}</span>
        <span className="home-sleeve-sealed-title">{ep.title}</span>
        <span className="home-sleeve-seal">Sealed: open to transcribe</span>
      </Link>
    )
  }
  const voices = item.detail ? voicesOf(item.detail) : []
  return (
    <Link to={`/episodes/${ep.id}`} className="home-sleeve home-sleeve--front">
      {item.detail ? <Groove ep={item.detail} voices={voices} /> : null}
      <span className="home-sleeve-show">{ep.podcast_title}</span>
      <span className="home-sleeve-num">{ep.number}</span>
      <span className="home-sleeve-name">{ep.title}</span>
    </Link>
  )
}

function BackSleeve({ item, depth }: { item: CrateItem; depth: number }) {
  return (
    <div
      className={`home-sleeve home-sleeve--back home-sleeve--d${depth} ${
        item.kind === 'sealed' ? 'home-sleeve--wrapped' : ''
      }`.trim()}
      aria-hidden="true"
    >
      {depth === 1 ? <span className="home-sleeve-back-title">{sleeveTitle(item.ep)}</span> : null}
      {depth === 1 && item.kind === 'sealed' ? (
        <span className="home-sleeve-seal home-sleeve-seal--sm">Sealed</span>
      ) : null}
    </div>
  )
}

function Crate({
  items,
  podcasts,
  loading,
}: {
  items: CrateItem[]
  podcasts: Podcast[]
  loading: boolean
}) {
  const [front, setFront] = useState(0)
  // 'out': the front sleeve tips back; 'in': the next one rises. The front link stays
  // mounted throughout, so keyboard focus survives a flip.
  const [phase, setPhase] = useState<'idle' | 'out' | 'in'>('idle')
  const timers = useRef<number[]>([])
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), [])
  const n = items.length
  const at = (k: number) => items[(((front + k) % n) + n) % n]!

  const goTo = (next: (f: number) => number) => {
    if (n < 2) return
    timers.current.forEach((t) => window.clearTimeout(t))
    if (reducedMotion()) {
      setFront(next)
      return
    }
    setPhase('out')
    timers.current = [
      window.setTimeout(() => {
        setFront(next)
        setPhase('in')
      }, FLIP_OUT_MS),
      window.setTimeout(() => setPhase('idle'), FLIP_OUT_MS + FLIP_IN_MS),
    ]
  }
  const flip = (step: number) => goTo((f) => (((f + step) % n) + n) % n)

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      flip(1)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      flip(-1)
    }
  }

  if (n === 0 && loading) {
    return <div className="home-crate home-crate--loading" aria-busy="true" aria-label="Loading the crate" />
  }

  if (n === 0) {
    return (
      <div className="home-crate home-crate--empty">
        <div className="home-tab home-tab--0">Empty bin</div>
        <div className="home-bin">
          <p className="home-bin-caption">
            Add a podcast and its episodes arrive here as sealed sleeves.{' '}
            <Link to="/library?tab=browse">Find your first podcast</Link>
          </p>
        </div>
      </div>
    )
  }

  const current = at(0)
  const detail = current.kind === 'record' ? current.detail : undefined
  const voices = detail ? voicesOf(detail).filter((v) => v.slot >= 0) : []
  const duration = detail?.segments.length
    ? detail.segments[detail.segments.length - 1]!.end
    : (current.ep.duration_seconds ?? 0)
  const tabs = podcasts.filter((p) => items.some((it) => it.ep.podcast_id === p.id)).slice(0, 3)

  return (
    <div
      className="home-crate"
      role="group"
      aria-roledescription="crate"
      aria-label={`Episodes, ${plural(n, 'sleeve')}. Use the arrow keys to flip.`}
      onKeyDown={onKey}
    >
      {n > 2 ? <BackSleeve item={at(2)} depth={2} /> : null}
      {n > 1 ? <BackSleeve item={at(1)} depth={1} /> : null}
      {tabs.map((p, i) => (
        <button
          key={p.id}
          type="button"
          className={`home-tab home-tab--${i}`}
          onClick={() => goTo(() => Math.max(0, items.findIndex((it) => it.ep.podcast_id === p.id)))}
        >
          {p.title}
        </button>
      ))}
      <div className={`home-front ${phase === 'idle' ? '' : `home-front--${phase}`}`.trim()}>
        <FrontSleeve item={current} />
      </div>
      {duration > 0 ? (
        <span className="home-sticker" aria-hidden="true">
          {fmtTime(duration)}
          <small>{detail ? plural(detail.segments.length, 'turn') : 'not yet heard'}</small>
        </span>
      ) : null}
      <div className="home-bin">
        <p className="home-bin-caption" aria-live="polite">
          {current.kind === 'record' && voices.length > 0 ? (
            <>
              The groove is the whole conversation:{' '}
              {voices.map((v, i) => (
                <span key={v.label}>
                  {i > 0 ? (i === voices.length - 1 ? ' and ' : ', ') : ''}
                  <i className={`home-swatch home-swatch--s${v.slot}`} aria-hidden="true" />
                  {v.name}
                </span>
              ))}
              .{items.some((it) => it.kind === 'sealed') ? ' Sealed sleeves are episodes not transcribed yet.' : ''}
            </>
          ) : current.kind === 'sealed' ? (
            <>Sealed sleeves are episodes not transcribed yet. Open one to process it.</>
          ) : (
            <>Loading the groove.</>
          )}
        </p>
        {n > 1 ? (
          <div className="home-flip">
            <button type="button" className="home-flip-btn" onClick={() => flip(-1)} aria-label="Previous sleeve">
              <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
                <path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </button>
            <button type="button" className="home-flip-btn" onClick={() => flip(1)} aria-label="Next sleeve">
              <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
                <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </button>
            <span className="home-flip-count">
              {fmtNumber(front + 1)} of {fmtNumber(n)}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ the wall

function Poster({ podcast, tilt }: { podcast: Podcast; tilt: number }) {
  const [failed, setFailed] = useState(false)
  return (
    <figure className={`home-poster home-poster--${tilt}`}>
      {failed ? (
        <div className="home-poster-type" aria-label={`${podcast.title} poster`}>
          <b>{podcast.title}</b>
          <i />
          <i />
          <i />
        </div>
      ) : (
        <img
          src={podcastPosterUrl(podcast.id)}
          alt={`${podcast.title} artwork`}
          onError={() => setFailed(true)}
          loading="lazy"
        />
      )}
      <figcaption title={`${podcast.title}: ${plural(podcast.episode_count, 'episode')}`}>
        {podcast.title} · {fmtNumber(podcast.episode_count)}
      </figcaption>
    </figure>
  )
}

// ------------------------------------------------------------------ the counter

function BookRack({ books }: { books: Book[] }) {
  if (books.length === 0) {
    return (
      <p className="home-empty">
        No books yet. Open a transcribed episode and choose Make a book; it lands here, covers out.
      </p>
    )
  }
  return (
    <ul className="home-rack">
      {books.map((b) => (
        <li key={b.id}>
          <a href={bookPdfUrl(b.id)} target="_blank" rel="noreferrer" className="home-rack-book">
            <img src={bookCoverUrl(b.id, `${b.seed}`)} alt={`Cover of ${b.title}`} loading="lazy" />
            <b>{b.title}</b>
            <span>
              {b.narrator ? `Told by ${b.narrator}` : 'Narrated'} · {plural(b.pages, 'page')}
            </span>
          </a>
        </li>
      ))}
    </ul>
  )
}

function AskForm({
  question,
  setQuestion,
  onSubmit,
  className,
}: {
  question: string
  setQuestion: (q: string) => void
  onSubmit: (e: FormEvent) => void
  className: string
}) {
  return (
    <form className={`home-ask ${className}`} onSubmit={onSubmit}>
      <input
        className="home-ask-input"
        aria-label="Ask a question about your podcast library"
        placeholder="What did they say about sleep?"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
      />
      <button type="submit" className="home-ask-btn">
        Ask
      </button>
    </form>
  )
}

export function HomePage() {
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const { data: stats } = useIndexStats()
  const { data: podcasts = [] } = usePodcasts()
  const { data: conversations } = useConversations()
  const { data: allBooks } = useBooks()
  const { data: quote } = useBookQuote()
  const { data: jobs } = useJobs()
  const indexed = useEpisodes({ status: 'indexed', limit: CRATE_INDEXED })
  const sealed = useEpisodes({ status: 'new', limit: CRATE_SEALED })

  const records = useMemo(() => indexed.data?.items ?? [], [indexed.data])
  const details = useCitedEpisodes(records.map((e) => e.id))
  const items = useMemo<CrateItem[]>(
    () => [
      ...records.map((ep) => ({ kind: 'record' as const, ep, detail: details.get(ep.id) })),
      ...(sealed.data?.items ?? []).map((ep) => ({ kind: 'sealed' as const, ep })),
    ],
    [records, details, sealed.data],
  )

  const books = allBooks ? allBooks.filter((b) => b.status === 'ready').slice(0, 3) : undefined
  const activeJob = (jobs ?? []).find(isJobActive)
  // While stats load, assume there is something to ask: never hide the primary action on a guess.
  const canAsk = !stats || stats.episodes_indexed > 0
  const lastChat = conversations?.[0]

  const lede = stats
    ? stats.podcasts === 0
      ? 'Add a podcast and every episode you transcribe becomes a record you can ask, and a book you can read.'
      : `${plural(stats.podcasts, 'show')}, ${plural(stats.episodes_total, 'episode')} in stock and ${fmtNumber(stats.episodes_indexed)} transcribed. Each one you transcribe becomes a record you can ask, and a book you can read.`
    : ''

  const ask = (e: FormEvent) => {
    e.preventDefault()
    const q = question.trim()
    navigate(q ? `/chat?q=${encodeURIComponent(q)}` : '/chat')
  }

  return (
    <main id="main-content" className="home">
      <section className="home-wall" aria-labelledby="home-title">
        <div className="home-intro">
          <h1 id="home-title" className="home-title">
            Dig through <em>everything</em> you&rsquo;ve heard.
          </h1>
          {lede ? <p className="home-lede">{lede}</p> : null}
          {canAsk ? (
            <>
              <AskForm
                question={question}
                setQuestion={setQuestion}
                onSubmit={ask}
                className="home-ask--wall"
              />
              <p className="home-ask-note home-ask-note--wall">Answers cite who said it, and when.</p>
            </>
          ) : null}
        </div>

        <div className="home-pinboard">
          {podcasts.slice(0, 2).map((p, i) => (
            <Poster key={p.id} podcast={p} tilt={i} />
          ))}
          {quote ? (
            <Link
              to={`/episodes/${quote.episode_id}?t=${Math.floor(quote.start)}`}
              className="home-pick"
              aria-label={`Staff pick: "${quote.text}", ${quote.speaker}, episode ${quote.episode_number} at ${fmtTime(quote.start)}`}
            >
              <span className="home-pick-pin" aria-hidden="true" />
              <span className="home-pick-quote">&ldquo;{quote.text}&rdquo;</span>
              <span className="home-stamp home-stamp--pick" aria-hidden="true">
                Staff pick
              </span>
              <span className="home-pick-meta">
                {quote.speaker} · {fmtEpNumber(quote.episode_number)} · {fmtTime(quote.start)}
              </span>
            </Link>
          ) : null}
        </div>

        <Crate items={items} podcasts={podcasts} loading={indexed.isPending || sealed.isPending} />
      </section>

      <aside className="home-counter" aria-label="The counter">
        <section className="home-block" aria-labelledby="home-books">
          <div className="home-block-head">
            <h2 id="home-books">New in: books</h2>
            <Link to="/books">All books</Link>
          </div>
          {books ? <BookRack books={books} /> : <div className="home-rack home-rack--loading" aria-busy="true" />}
        </section>

        <section className="home-block home-block--ask" aria-labelledby="home-ask">
          <div className="home-block-head">
            <h2 id="home-ask">Ask the counter</h2>
            <Link to="/chat">All chats</Link>
          </div>
          {canAsk ? (
            <>
              <AskForm question={question} setQuestion={setQuestion} onSubmit={ask} className="home-ask--counter" />
              <p className="home-ask-note">Answers cite who said it, and when.</p>
            </>
          ) : (
            <p className="home-empty">
              Nothing to ask yet: transcribe an episode first.{' '}
              <Link to="/library?tab=browse">Find a podcast</Link>
            </p>
          )}
        </section>

        <div className="home-slips">
          {lastChat ? (
            <Link to={`/chat/${lastChat.id}`} className="home-slip">
              <span className="home-stamp" aria-hidden="true">
                On hold
              </span>
              <span className="home-slip-main">{lastChat.title}</span>
              <span className="home-slip-meta">
                <span className="sr-only">On hold: your last chat, </span>
                {fmtRelativeDate(lastChat.updated_at)}
              </span>
            </Link>
          ) : (
            <div className="home-slip" aria-busy={conversations ? undefined : true}>
              <span className="home-stamp" aria-hidden="true">
                On hold
              </span>
              <span className="home-slip-main">{conversations ? 'No chats yet' : '\u00a0'}</span>
              <span className="home-slip-meta">{conversations ? 'Your conversations wait here.' : '\u00a0'}</span>
            </div>
          )}
          {activeJob ? (
            <Link to="/jobs" className="home-slip home-slip--live">
              <span className="home-stamp" aria-hidden="true">
                Back room
              </span>
              <span className="home-slip-main">{activeJob.episode_title ?? 'Working'}</span>
              <span className="home-slip-meta">{activeJob.message || 'Queued'}</span>
              <span className="home-slip-progress" aria-hidden="true">
                <span style={{ width: `${Math.round(Math.max(0.04, activeJob.progress) * 100)}%` }} />
              </span>
            </Link>
          ) : (
            <Link to="/library" className="home-slip">
              <span className="home-stamp" aria-hidden="true">
                Back room
              </span>
              <span className="home-slip-main">{jobs ? 'Nothing processing' : '\u00a0'}</span>
              <span className="home-slip-meta">
                {stats ? `${plural(stats.episodes_total - stats.episodes_indexed, 'episode')} still sealed` : '\u00a0'}
              </span>
            </Link>
          )}
        </div>
      </aside>
    </main>
  )
}
