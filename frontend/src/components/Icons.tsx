/**
 * Minimal stroke SVG icons (< 24px, 1.5px stroke, no unicode/emoji).
 */

interface IconProps {
  size?: number
  className?: string
}

export function IconChat({ size = 18, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 3.75h12a1 1 0 0 1 1 1v7.5a1 1 0 0 1-1 1H7l-3.5 2.5v-2.5H3a1 1 0 0 1-1-1v-7.5a1 1 0 0 1 1-1Z" />
      <path d="M5.5 7.25h7M5.5 9.75h4.5" />
    </svg>
  )
}

export function IconLibrary({ size = 18, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3.25 3v12M7.25 3v12M11.25 3.5l3.5 11.25" />
      <path d="M2.25 15h13.5" />
    </svg>
  )
}

export function IconJobs({ size = 18, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="2.5" y="3.25" width="13" height="3.25" rx="0.75" />
      <rect x="2.5" y="8.25" width="13" height="3.25" rx="0.75" />
      <path d="M2.5 14.5h8.5" />
    </svg>
  )
}

export function IconPlus({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M8 3v10M3 8h10" />
    </svg>
  )
}

export function IconChevronDown({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="m4 6 4 4 4-4" />
    </svg>
  )
}

export function IconSearch({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <circle cx="7" cy="7" r="4.25" />
      <path d="m10.25 10.25 3.25 3.25" />
    </svg>
  )
}

export function IconStop({ size = 12, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      <rect x="3" y="3" width="10" height="10" rx="1.5" />
    </svg>
  )
}

export function IconEdit({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M10.75 2.75 13.25 5.25 5.5 13H3v-2.5l7.75-7.75Z" />
    </svg>
  )
}

export function IconTrash({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 4.5h10M6 4.5V3h4v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" />
    </svg>
  )
}

export function IconCheck({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="m3.5 8.5 3 3 6-6.5" />
    </svg>
  )
}

export function IconClose({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="m4 4 8 8M12 4l-8 8" />
    </svg>
  )
}

export function IconRefresh({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M13 4v3.5H9.5" />
      <path d="M12.6 7.5a5 5 0 1 0 .6 3.5" />
    </svg>
  )
}

export function IconExternalLink({ size = 13, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M9.5 3H13v3.5M13 3 7.5 8.5" />
      <path d="M11 9v3.5a.5.5 0 0 1-.5.5h-7a.5.5 0 0 1-.5-.5v-7a.5.5 0 0 1 .5-.5H7" />
    </svg>
  )
}

export function IconSidebar({ size = 15, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="2" y="2.75" width="12" height="10.5" rx="1.25" />
      <path d="M6 2.75v10.5" />
    </svg>
  )
}

export function IconBook({ size = 18, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M9 4.5C7.6 3.4 5.4 3 2.75 3.25v10.5c2.65-.25 4.85.15 6.25 1.25 1.4-1.1 3.6-1.5 6.25-1.25V3.25C12.6 3 10.4 3.4 9 4.5z" />
      <path d="M9 4.5V15" />
    </svg>
  )
}

export function IconDownload({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M7 1.75v7.5M4 6.5 7 9.5l3-3M2.25 11.75h9.5" />
    </svg>
  )
}

export function IconShuffle({ size = 14, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M1.75 4h2.1c1.3 0 2.5.7 3.15 1.8l.75 1.4c.65 1.1 1.85 1.8 3.15 1.8h1.35M10.75 7.5 12.25 9l-1.5 1.5" />
      <path d="M1.75 10h2.1c.8 0 1.6-.3 2.2-.75M8.35 4.75c.6-.45 1.4-.75 2.2-.75h1.7M10.75 2.5 12.25 4l-1.5 1.5" />
    </svg>
  )
}
