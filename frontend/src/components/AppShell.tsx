import type { ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { isJobActive, useJobs } from '../api/hooks'
import { fmtNumber } from '../utils/format'
import { IconChat, IconJobs, IconLibrary } from './Icons'
import './AppShell.css'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const location = useLocation()
  const { data: jobs } = useJobs()
  const activeJobsCount = jobs ? jobs.filter(isJobActive).length : 0

  const isChatRoute = location.pathname === '/' || location.pathname.startsWith('/c/')
  const isLibraryRoute =
    location.pathname.startsWith('/library') || location.pathname.startsWith('/episodes/')

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <nav className="app-rail" aria-label="Primary">
        <Link to="/" className="app-logo" aria-label="Recall — Chat home">
          R
        </Link>

        <div className="app-nav-links">
          <NavLink
            to="/"
            end
            className={() => `app-nav-link ${isChatRoute ? 'app-nav-link--on' : ''}`.trim()}
          >
            <IconChat size={18} />
            <span>Chat</span>
          </NavLink>

          <NavLink
            to="/library"
            className={() => `app-nav-link ${isLibraryRoute ? 'app-nav-link--on' : ''}`.trim()}
          >
            <IconLibrary size={18} />
            <span>Library</span>
          </NavLink>

          <NavLink
            to="/jobs"
            className={({ isActive }) =>
              `app-nav-link ${isActive ? 'app-nav-link--on' : ''}`.trim()
            }
          >
            <span className="app-nav-icon-wrap">
              <IconJobs size={18} />
              {activeJobsCount > 0 ? (
                <span
                  className="app-nav-badge"
                  aria-label={`${fmtNumber(activeJobsCount)} active ${activeJobsCount === 1 ? 'job' : 'jobs'}`}
                >
                  {fmtNumber(activeJobsCount)}
                </span>
              ) : null}
            </span>
            <span>Jobs</span>
          </NavLink>
        </div>
      </nav>

      <div className="app-workspace">{children}</div>
    </div>
  )
}
