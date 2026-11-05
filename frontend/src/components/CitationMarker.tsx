import type { Citation } from '../api/types'
import { fmtTime } from '../utils/format'
import './CitationMarker.css'

interface CitationMarkerProps {
  n: number
  citation?: Citation
  active: boolean
  onActivate: (n: number | null) => void
  onSelect: (n: number, citation?: Citation) => void
}

export function CitationMarker({
  n,
  citation,
  active,
  onActivate,
  onSelect,
}: CitationMarkerProps) {
  const ariaLabel = citation
    ? `Citation ${n}: ${citation.episode_title}, ${citation.speaker} at ${fmtTime(citation.start)}`
    : `Citation ${n}`

  return (
    <button
      type="button"
      className={`citation-marker ${active ? 'citation-marker--live' : ''}`.trim()}
      aria-label={ariaLabel}
      onMouseEnter={() => onActivate(n)}
      onMouseLeave={() => onActivate(null)}
      onFocus={() => onActivate(n)}
      onBlur={() => onActivate(null)}
      onClick={() => onSelect(n, citation)}
    >
      {n}
    </button>
  )
}
