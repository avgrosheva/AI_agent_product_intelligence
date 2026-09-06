import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { Overview } from './pages/Overview'
import { Experiment } from './pages/Experiment'
import { Investigation } from './pages/Investigation'
import { Sessions } from './pages/Sessions'
import { SessionDetail } from './pages/SessionDetail'
import { AIQuality } from './pages/AIQuality'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/experiments/:experimentId" element={<Experiment />} />
        <Route path="/experiments/:experimentId/investigation" element={<Investigation />} />
        <Route path="/experiments/:experimentId/ai-quality" element={<AIQuality />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/sessions/:sessionId" element={<SessionDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
