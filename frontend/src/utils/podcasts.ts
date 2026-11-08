import type { Podcast } from '../api/types'

/** A local show holding uploaded audio files (no feed to refresh). */
export function isUploadShow(p: Pick<Podcast, 'rss_url'>): boolean {
  return p.rss_url.startsWith('upload://')
}
