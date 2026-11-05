import { useState, type KeyboardEvent, type MouseEvent } from 'react'
import type { Segment } from '../api/types'
import { fmtTime } from '../utils/format'
import { getSpeakerColor, speakerDisplayName } from '../utils/speakers'
import './SpeakerStrip.css'

interface SpeakerBlock {
  key: string
  leftPct: number
  widthPct: number
  color: string
  speakerName: string
  start: number
  end: number
}

interface SpeakerStripProps {
  segments?: readonly Segment[]
  speakers?: Record<string, string>
  colorMap?: ReadonlyMap<string, string>
  /** Start of visible window in seconds (0 on Episode page, passage window in ReferenceList). */
  windowStart?: number
  /** End of visible window in seconds. */
  windowEnd?: number
  /** Fallback speaker name when full segments are not available yet. */
  fallbackSpeaker?: string
  /** Current playback time in seconds (Episode page). */
  currentTime?: number
  /** Seek handler — makes the strip interactive when provided. */
  onSeek?: (seconds: number) => void
  variant?: 'compact' | 'full'
  /** Resting hint under an interactive strip; describe what a click actually does. */
  hint?: string
}

export function SpeakerStrip({
  segments,
  speakers,
  colorMap,
  windowStart = 0,
  windowEnd,
  fallbackSpeaker,
  currentTime,
  onSeek,
  variant = 'compact',
  hint = 'Click the timeline to seek',
}: SpeakerStripProps) {
  const [hoverInfo, setHoverInfo] = useState<string | null>(null)

  const lastSegEnd =
    segments && segments.length > 0 ? segments[segments.length - 1]!.end : 0

  let rangeStart = Math.max(0, windowStart)
  let rangeEnd =
    windowEnd !== undefined && windowEnd > rangeStart
      ? windowEnd
      : Math.max(lastSegEnd, rangeStart + 1)

  // In compact reference mode, expand slightly around the passage when episode segments exist
  // so surrounding speaker turns are visible in exact time proportion.
  if (variant === 'compact' && segments && segments.length > 0) {
    const passageSpan = Math.max(5, rangeEnd - rangeStart)
    const pad = Math.min(30, passageSpan * 0.4)
    rangeStart = Math.max(0, rangeStart - pad)
    rangeEnd = lastSegEnd > 0 ? Math.min(lastSegEnd, rangeEnd + pad) : rangeEnd + pad
    if (rangeEnd <= rangeStart) {
      rangeEnd = rangeStart + 1
    }
  }

  const span = Math.max(0.1, rangeEnd - rangeStart)
  const blocks: SpeakerBlock[] = []

  if (segments && segments.length > 0) {
    for (let i = 0; i < segments.length; i += 1) {
      const seg = segments[i]!
      if (seg.end <= rangeStart || seg.start >= rangeEnd) continue
      const clippedStart = Math.max(rangeStart, seg.start)
      const clippedEnd = Math.min(rangeEnd, seg.end)
      const dur = clippedEnd - clippedStart
      if (dur <= 0) continue

      blocks.push({
        key: `${i}-${seg.start}`,
        leftPct: ((clippedStart - rangeStart) / span) * 100,
        widthPct: Math.max(0.25, (dur / span) * 100),
        color: getSpeakerColor(seg.speaker, colorMap),
        speakerName: speakerDisplayName(seg.speaker, speakers),
        start: seg.start,
        end: seg.end,
      })
    }
  }

  if (blocks.length === 0 && fallbackSpeaker) {
    blocks.push({
      key: 'fallback',
      leftPct: 0,
      widthPct: 100,
      color: getSpeakerColor(fallbackSpeaker, colorMap),
      speakerName: fallbackSpeaker,
      start: rangeStart,
      end: rangeEnd,
    })
  }

  if (variant === 'compact' || !onSeek) {
    return (
      <div className="speaker-strip speaker-strip--compact" aria-hidden="true">
        {blocks.map((b) => (
          <span
            key={b.key}
            className="speaker-strip-turn"
            style={{
              left: `${b.leftPct}%`,
              width: `${b.widthPct}%`,
              backgroundColor: b.color,
            }}
          />
        ))}
      </div>
    )
  }

  const playheadPct =
    currentTime !== undefined && Number.isFinite(currentTime)
      ? Math.max(0, Math.min(100, ((currentTime - rangeStart) / span) * 100))
      : null

  const resolveSecondsFromPointer = (e: MouseEvent<HTMLDivElement>): number => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width <= 0) return rangeStart
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    return rangeStart + ratio * span
  }

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    onSeek(resolveSecondsFromPointer(e))
  }

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    const sec = resolveSecondsFromPointer(e)
    const hit = segments?.find((s) => sec >= s.start && sec <= s.end)
    const spName = hit ? speakerDisplayName(hit.speaker, speakers) : null
    setHoverInfo(spName ? `${spName} · ${fmtTime(sec)}` : fmtTime(sec))
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const cur = currentTime ?? rangeStart
    const step = e.shiftKey ? 30 : 10
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      onSeek(Math.min(rangeEnd, cur + step))
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      onSeek(Math.max(rangeStart, cur - step))
    } else if (e.key === 'Home') {
      e.preventDefault()
      onSeek(rangeStart)
    } else if (e.key === 'End') {
      e.preventDefault()
      onSeek(rangeEnd)
    }
  }

  return (
    <div className="speaker-strip-container">
      <div
        className="speaker-strip speaker-strip--full"
        role="slider"
        tabIndex={0}
        aria-label="Episode speaker timeline"
        aria-valuemin={Math.round(rangeStart)}
        aria-valuemax={Math.round(rangeEnd)}
        aria-valuenow={Math.round(currentTime ?? rangeStart)}
        aria-valuetext={`${fmtTime(currentTime ?? rangeStart)} of ${fmtTime(rangeEnd)}`}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverInfo(null)}
        onKeyDown={handleKeyDown}
      >
        {blocks.map((b) => (
          <span
            key={b.key}
            className="speaker-strip-turn"
            style={{
              left: `${b.leftPct}%`,
              width: `${b.widthPct}%`,
              backgroundColor: b.color,
            }}
          />
        ))}
        {playheadPct !== null ? (
          <span
            className="speaker-strip-playhead"
            style={{ left: `${playheadPct}%` }}
            aria-hidden="true"
          />
        ) : null}
      </div>
      <div className="speaker-strip-meta">
        <span>{fmtTime(rangeStart)}</span>
        <span className="speaker-strip-hover">{hoverInfo ?? hint}</span>
        <span>{fmtTime(rangeEnd)}</span>
      </div>
    </div>
  )
}
