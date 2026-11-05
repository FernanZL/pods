import type { Segment } from '../api/types'

const SPEAKER_TOKENS = [
  'var(--speaker-1)',
  'var(--speaker-2)',
  'var(--speaker-3)',
  'var(--speaker-4)',
] as const

const SPEAKER_FALLBACK = 'var(--speaker-other)'

/** Resolve a human-readable speaker name from a transcript label ("A" -> "Andrew Huberman"). */
export function speakerDisplayName(label: string, speakers?: Record<string, string>): string {
  const trimmed = label.trim()
  if (!trimmed) return 'Speaker'
  if (speakers && speakers[trimmed]) {
    return speakers[trimmed]
  }
  if (/^speaker\s+/i.test(trimmed)) {
    return trimmed
  }
  if (trimmed.length <= 2) {
    return `Speaker ${trimmed}`
  }
  return trimmed
}

/**
 * Build a map from both speaker keys ("A", "B") and display names ("Andrew Huberman")
 * to --speaker-1..4 in order of first appearance per episode.
 */
export function buildSpeakerColorMap(
  speakers?: Record<string, string>,
  segments?: readonly Segment[],
): Map<string, string> {
  const map = new Map<string, string>()
  let idx = 0

  const assign = (key: string, displayName?: string) => {
    if (!key) return
    if (map.has(key)) {
      if (displayName && !map.has(displayName)) {
        map.set(displayName, map.get(key)!)
      }
      return
    }
    if (displayName && map.has(displayName)) {
      map.set(key, map.get(displayName)!)
      return
    }
    const token = idx < SPEAKER_TOKENS.length ? SPEAKER_TOKENS[idx] : SPEAKER_FALLBACK
    idx += 1
    map.set(key, token)
    if (displayName) {
      map.set(displayName, token)
    }
  }

  if (speakers) {
    for (const [label, name] of Object.entries(speakers)) {
      assign(label, name)
    }
  }

  if (segments) {
    for (const seg of segments) {
      const display = speakerDisplayName(seg.speaker, speakers)
      assign(seg.speaker, display)
    }
  }

  return map
}

/** Look up a speaker's CSS color variable from a color map with fallback. */
export function getSpeakerColor(speaker: string, colorMap?: ReadonlyMap<string, string>): string {
  if (!speaker || !colorMap) return SPEAKER_TOKENS[0]
  return colorMap.get(speaker) ?? SPEAKER_FALLBACK
}

/** Build a fallback color map across plain speaker display names in order of appearance. */
export function buildNamesColorMap(names: readonly string[]): Map<string, string> {
  const map = new Map<string, string>()
  let idx = 0
  for (const name of names) {
    if (!name || map.has(name)) continue
    const token = idx < SPEAKER_TOKENS.length ? SPEAKER_TOKENS[idx] : SPEAKER_FALLBACK
    idx += 1
    map.set(name, token)
  }
  return map
}
