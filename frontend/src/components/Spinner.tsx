import './Spinner.css'

interface SpinnerProps {
  size?: number
  label?: string
}

export function Spinner({ size = 14, label = 'Loading' }: SpinnerProps) {
  return (
    <span className="spinner-wrap" role="status" aria-label={label}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 16 16"
        fill="none"
        className="spinner-svg"
        aria-hidden="true"
      >
        <circle
          cx="8"
          cy="8"
          r="6"
          stroke="currentColor"
          strokeOpacity="0.25"
          strokeWidth="2"
        />
        <path
          d="M14 8a6 6 0 0 0-6-6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  )
}

interface SkeletonProps {
  width?: string
  height?: string
  className?: string
}

export function Skeleton({ width = '100%', height = '14px', className = '' }: SkeletonProps) {
  return (
    <span
      className={`skeleton-bar ${className}`.trim()}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}
