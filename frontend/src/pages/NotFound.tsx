import { Link } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import './NotFound.css'

export function NotFound() {
  return (
    <main id="main-content" className="page-container not-found-page">
      <EmptyState
        title="Page not found"
        description="The address you requested does not match a view in Recall."
        action={
          <>
            <Link to="/" className="btn btn-primary">
              Back to Chat
            </Link>
            <Link to="/library" className="btn">
              Open Library
            </Link>
          </>
        }
      />
    </main>
  )
}
