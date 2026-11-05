import type { AppConfig, IndexStats, Scope } from '../api/types'
import { fmtHours, fmtNumber } from '../utils/format'
import { IconSidebar } from './Icons'
import { ScopePicker } from './ScopePicker'
import { Skeleton } from './Spinner'
import { StatusStamp } from './StatusStamp'
import './IndexStrip.css'

interface IndexStripProps {
  stats: IndexStats | undefined
  statsLoading: boolean
  config: AppConfig | undefined
  scope: Scope
  onScopeChange: (next: Scope) => void
  onOpenConversations?: () => void
}

export function IndexStrip({
  stats,
  statsLoading,
  config,
  scope,
  onScopeChange,
  onOpenConversations,
}: IndexStripProps) {
  return (
    <div className="index-strip">
      {onOpenConversations ? (
        <button
          type="button"
          className="btn btn-sm index-strip-drawer-btn"
          onClick={onOpenConversations}
          aria-label="Open conversations list"
        >
          <IconSidebar size={14} />
          <span>Conversations</span>
        </button>
      ) : null}

      <div className="index-strip-metrics">
        {statsLoading && !stats ? (
          <Skeleton width="260px" height="15px" />
        ) : stats ? (
          <>
            <span className="index-strip-item">
              <strong className="index-strip-num">{fmtNumber(stats.episodes_indexed)}</strong>{' '}
              {stats.episodes_indexed === 1 ? 'episode indexed' : 'episodes indexed'}
            </span>
            <span className="index-strip-dot" aria-hidden="true">
              ·
            </span>
            <span className="index-strip-item">
              <strong className="index-strip-num">{fmtNumber(stats.passages)}</strong>{' '}
              {stats.passages === 1 ? 'passage' : 'passages'}
            </span>
            <span className="index-strip-dot" aria-hidden="true">
              ·
            </span>
            <span className="index-strip-item">
              <strong className="index-strip-num">{fmtHours(stats.hours_indexed)}</strong> h
            </span>
          </>
        ) : (
          <span className="index-strip-item">Index status unavailable</span>
        )}
        {config?.fake_mode ? <StatusStamp status="demo" /> : null}
      </div>

      <div className="index-strip-right">
        <ScopePicker
          scope={scope}
          onChange={onScopeChange}
          disabled={Boolean(stats && stats.episodes_indexed === 0)}
        />
      </div>
    </div>
  )
}
