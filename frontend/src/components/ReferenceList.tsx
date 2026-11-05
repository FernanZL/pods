import { useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useCitedEpisodes } from '../api/hooks'
import type { Citation } from '../api/types'
import { fmtEpNumber, fmtTime } from '../utils/format'
import { buildNamesColorMap, buildSpeakerColorMap, getSpeakerColor } from '../utils/speakers'
import { SpeakerStrip } from './SpeakerStrip'
import './ReferenceList.css'

interface ReferenceListProps {
  citations: readonly Citation[]
  activeN: number | null
  onActivate: (n: number | null) => void
  streaming?: boolean
  idPrefix?: string
}

export function ReferenceList({
  citations,
  activeN,
  onActivate,
  streaming = false,
  idPrefix = 'ref',
}: ReferenceListProps) {
  const episodeIds = useMemo(() => citations.map((c) => c.episode_id), [citations])
  const citedEpisodes = useCitedEpisodes(episodeIds)
  const fallbackColorMap = useMemo(
    () => buildNamesColorMap(citations.map((c) => c.speaker)),
    [citations],
  )
  const itemRefs = useRef<Map<number, HTMLLIElement>>(new Map())

  useEffect(() => {
    if (activeN === null) return
    const el = itemRefs.current.get(activeN)
    if (el) {
      el.scrollIntoView({ block: 'nearest' })
    }
  }, [activeN])

  const episodeColorMaps = useMemo(() => {
    const map = new Map<number, ReadonlyMap<string, string>>()
    for (const [id, ep] of citedEpisodes.entries()) {
      map.set(id, buildSpeakerColorMap(ep.speakers, ep.segments))
    }
    return map
  }, [citedEpisodes])

  if (citations.length === 0) {
    return (
      <p className="ref-empty">
        {streaming
          ? 'Retrieving candidate passages from your library…'
          : 'Sources cited in the answer appear here with speaker turns and timestamps.'}
      </p>
    )
  }

  return (
    <ol className="ref-list">
      {citations.map((c) => {
        const ep = citedEpisodes.get(c.episode_id)
        const epColorMap = episodeColorMaps.get(c.episode_id) ?? fallbackColorMap
        const speakerColor = getSpeakerColor(c.speaker, epColorMap)
        const epLabel = fmtEpNumber(c.episode_number || ep?.number || null)
        const isLive = activeN === c.n
        const isDimmed = activeN !== null && activeN !== c.n
        const seekSec = Math.max(0, Math.floor(c.start))

        const itemClass = [
          'ref-entry',
          isLive ? 'ref-entry--live' : '',
          isDimmed ? 'ref-entry--dimmed' : '',
        ]
          .filter(Boolean)
          .join(' ')

        return (
          <li
            key={`${c.n}-${c.episode_id}-${c.start}`}
            id={`${idPrefix}-${c.n}`}
            ref={(node) => {
              if (node) {
                itemRefs.current.set(c.n, node)
              } else {
                itemRefs.current.delete(c.n)
              }
            }}
            className={itemClass}
          >
            <Link
              to={`/episodes/${c.episode_id}?t=${seekSec}`}
              className="ref-entry-link"
              onMouseEnter={() => onActivate(c.n)}
              onMouseLeave={() => onActivate(null)}
              onFocus={() => onActivate(c.n)}
              onBlur={() => onActivate(null)}
            >
              <span className={`ref-num ${isLive ? 'ref-num--live' : ''}`.trim()}>{c.n}</span>
              <div className="ref-body">
                <span className="ref-title">
                  <span className="ref-ep-prefix">{epLabel}</span> · {c.episode_title}
                </span>
                <span className="ref-meta">
                  <span
                    className="ref-speaker-swatch"
                    style={{ backgroundColor: speakerColor }}
                    aria-hidden="true"
                  />
                  {c.source === 'summary' ? (
                    <span>Episode summary · {c.podcast_title}</span>
                  ) : (
                    <span>
                      {c.speaker} · {fmtTime(c.start)}–{fmtTime(c.end)}
                    </span>
                  )}
                </span>
                <SpeakerStrip
                  segments={c.source === 'transcript' ? ep?.segments : undefined}
                  speakers={ep?.speakers}
                  colorMap={epColorMap}
                  windowStart={c.start}
                  windowEnd={Math.max(c.end, c.start + 1)}
                  fallbackSpeaker={c.speaker}
                  variant="compact"
                />
                {isLive && c.snippet ? <p className="ref-snippet">{c.snippet}</p> : null}
              </div>
            </Link>
          </li>
        )
      })}
    </ol>
  )
}
