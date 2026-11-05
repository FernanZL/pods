import { IconClose } from './Icons'
import './ErrorBanner.css'

interface ErrorBannerProps {
  message: string
  recovery?: string
  onRetry?: () => void
  retryLabel?: string
  onDismiss?: () => void
}

export function ErrorBanner({
  message,
  recovery,
  onRetry,
  retryLabel = 'Retry',
  onDismiss,
}: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <div className="error-banner-text">
        <strong className="error-banner-msg">{message}</strong>
        {recovery ? <span className="error-banner-recovery"> {recovery}</span> : null}
      </div>
      {onRetry || onDismiss ? (
        <div className="error-banner-actions">
          {onRetry ? (
            <button type="button" className="btn btn-sm" onClick={onRetry}>
              {retryLabel}
            </button>
          ) : null}
          {onDismiss ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onDismiss}
              aria-label="Dismiss error"
            >
              <IconClose size={13} />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
