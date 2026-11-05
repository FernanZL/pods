import { Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ToastProvider } from './components/ToastProvider'
import { ChatPage } from './pages/ChatPage'
import { EpisodePage } from './pages/EpisodePage'
import { JobsPage } from './pages/JobsPage'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { NotFound } from './pages/NotFound'
import './App.css'

function AppLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

/** Old conversation links (/c/:id) keep working. */
function LegacyConversationRedirect() {
  const { conversationId } = useParams()
  return <Navigate to={`/chat/${conversationId ?? ''}`} replace />
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/chat" element={<ChatPage />}>
            <Route index element={null} />
            <Route path=":conversationId" element={null} />
          </Route>
          <Route path="/c/:conversationId" element={<LegacyConversationRedirect />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/episodes/:id" element={<EpisodePage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </ToastProvider>
  )
}
