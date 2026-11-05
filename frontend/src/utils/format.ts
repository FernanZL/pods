/**
 * Formatting helpers for timestamps, durations, currencies, episode catalog numbers,
 * dates, and safe external URL validation.
 */

/** Format seconds into "m:ss" or "h:mm:ss" (tabular-ready). */
export function fmtTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '0:00'
  }
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Format an episode or job duration into a compact readable string. */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) {
    return '—'
  }
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) {
    return `${h}h ${String(m).padStart(2, '0')}m`
  }
  if (m > 0) {
    return `${m}m ${String(s).padStart(2, '0')}s`
  }
  return `${s}s`
}

/** Format USD cost honestly, preserving sub-cent precision when > 0 and < $0.01. */
export function fmtUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) {
    return '$0.00'
  }
  if (amount < 0.01) {
    return `$${amount.toFixed(4)}`
  }
  if (amount < 0.1) {
    return `$${amount.toFixed(3)}`
  }
  return `$${amount.toFixed(2)}`
}

/** Format an episode catalog number as "Ep. 0213" (4-digit zero-padded). */
export function fmtEpNumber(num: number | null | undefined): string {
  if (num === null || num === undefined || !Number.isFinite(num) || num <= 0) {
    return 'Ep. —'
  }
  return `Ep. ${String(Math.trunc(num)).padStart(4, '0')}`
}

/** Format an integer count with thousands separators. */
export function fmtNumber(n: number): string {
  if (!Number.isFinite(n)) return '0'
  return Math.trunc(n).toLocaleString('en-US')
}

/** Format indexed hours to one decimal place. */
export function fmtHours(hours: number): string {
  if (!Number.isFinite(hours) || hours <= 0) return '0.0'
  return hours.toFixed(1)
}

const SHORT_MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

/** Format an ISO timestamp as "2 Nov 2026" (or "—" if absent). */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getDate()} ${SHORT_MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** Format an ISO timestamp for conversation lists ("Today", "Yesterday", "2 Nov"). */
export function fmtRelativeDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfTarget = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfToday - startOfTarget) / 86_400_000)

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getDate()} ${SHORT_MONTHS[d.getMonth()]}`
  }
  return `${d.getDate()} ${SHORT_MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** Format elapsed seconds between two ISO timestamps (or until now). */
export function fmtElapsed(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): string {
  if (!startedAt) return '—'
  const startMs = new Date(startedAt).getTime()
  if (Number.isNaN(startMs)) return '—'
  const endMs = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  if (Number.isNaN(endMs) || endMs < startMs) return '0s'
  return fmtDuration((endMs - startMs) / 1000)
}

/** Return the URL only if it uses http: or https:, preventing unsafe scheme injection. */
export function safeExternalUrl(raw: string | null | undefined): string | null {
  if (!raw) return null
  try {
    const parsed = new URL(raw)
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.toString()
    }
    return null
  } catch {
    return null
  }
}
