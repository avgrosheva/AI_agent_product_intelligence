import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { RequireAuth } from './components/layout/RequireAuth'
import { Overview } from './pages/Overview'
import { Experiment } from './pages/Experiment'
import { Investigation } from './pages/Investigation'
import { ReleaseDecision } from './pages/ReleaseDecision'
import { Sessions } from './pages/Sessions'
import { SessionDetail } from './pages/SessionDetail'
import { AIQuality } from './pages/AIQuality'
import { Login } from './pages/Login'
import { ActiveExperimentProvider } from './state/ActiveExperimentContext'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <ActiveExperimentProvider>
              <AppLayout />
            </ActiveExperimentProvider>
          </RequireAuth>
        }
      >
        <Route path="/" element={<Overview />} />
        <Route path="/experiments/:experimentId" element={<Experiment />} />
        <Route path="/experiments/:experimentId/investigation" element={<Investigation />} />
        <Route path="/experiments/:experimentId/release" element={<ReleaseDecision />} />
        <Route path="/experiments/:experimentId/ai-quality" element={<AIQuality />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/sessions/:sessionId" element={<SessionDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
