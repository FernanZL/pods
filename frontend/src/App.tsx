import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ToastProvider } from './components/ToastProvider'
import { ChatPage } from './pages/ChatPage'
import { EpisodePage } from './pages/EpisodePage'
import { JobsPage } from './pages/JobsPage'
import { LibraryPage } from './pages/LibraryPage'
import { NotFound } from './pages/NotFound'
import './App.css'

export default function App() {
  return (
    <ToastProvider>
      <AppShell>
        <Routes>
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/episodes/:id" element={<EpisodePage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/" element={<ChatPage />}>
            <Route index element={null} />
            <Route path="c/:conversationId" element={null} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AppShell>
    </ToastProvider>
  )
}
