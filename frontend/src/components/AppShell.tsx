import { useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { isJobActive, useJobs } from '../api/hooks'
import { fmtNumber } from '../utils/format'
import { IconBook, IconChat, IconJobs, IconLibrary } from './Icons'
import { TopbarSlotContext } from './topbarSlot'
import './AppShell.css'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation()
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  const { data: jobs } = useJobs()
  const activeJobsCount = jobs ? jobs.filter(isJobActive).length : 0

  const isChatRoute = location.pathname.startsWith('/chat')
  const isLibraryRoute =
    location.pathname.startsWith('/library') || location.pathname.startsWith('/episodes/')

  const linkClass = (on: boolean) => `app-nav-link ${on ? 'app-nav-link--on' : ''}`.trim()

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <header className="app-topbar">
        <Link to="/" className="app-brand" aria-label="Pods home">
          <span className="app-logo" aria-hidden="true">
            P
          </span>
          <span className="app-wordmark">Pods</span>
        </Link>

        <nav className="app-nav-links" aria-label="Primary">
          <NavLink to="/chat" className={() => linkClass(isChatRoute)}>
            <IconChat size={16} />
            <span>Chat</span>
          </NavLink>
          <NavLink to="/library" className={() => linkClass(isLibraryRoute)}>
            <IconLibrary size={16} />
            <span>Library</span>
          </NavLink>
          <NavLink to="/books" className={({ isActive }) => linkClass(isActive)}>
            <IconBook size={16} />
            <span>Books</span>
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => linkClass(isActive)}>
            <IconJobs size={16} />
            <span>Jobs</span>
            {activeJobsCount > 0 ? (
              <span
                className="app-nav-badge"
                aria-label={`${fmtNumber(activeJobsCount)} active ${activeJobsCount === 1 ? 'job' : 'jobs'}`}
              >
                {fmtNumber(activeJobsCount)}
              </span>
            ) : null}
          </NavLink>
        </nav>

        <div className="app-topbar-slot" ref={setSlot} />
      </header>

      <TopbarSlotContext.Provider value={slot}>
        <div className="app-workspace">{children}</div>
      </TopbarSlotContext.Provider>
    </div>
  )
}
