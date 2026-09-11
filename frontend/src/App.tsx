import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { RequireAuth } from './components/layout/RequireAuth'
import { ScrollToTop } from './components/layout/ScrollToTop'
import { Landing } from './pages/Landing'
import { Overview } from './pages/Overview'
import { Register } from './pages/Register'
import { Experiment } from './pages/Experiment'
import { Investigation } from './pages/Investigation'
import { ReleaseDecision } from './pages/ReleaseDecision'
import { Sessions } from './pages/Sessions'
import { SessionDetail } from './pages/SessionDetail'
import { AIQuality } from './pages/AIQuality'
import { Alerts } from './pages/Alerts'
import { ReviewQueue } from './pages/ReviewQueue'
import { Login } from './pages/Login'
import { OnboardingPage } from './pages/onboarding/OnboardingPage'
import { ProjectOverview } from './pages/ProjectOverview'
import { ActiveExperimentProvider } from './state/ActiveExperimentContext'
import { ActiveProjectProvider } from './state/ActiveProjectContext'

export function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/welcome" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          element={
            <RequireAuth>
              <ActiveProjectProvider>
                <ActiveExperimentProvider>
                  <AppLayout />
                </ActiveExperimentProvider>
              </ActiveProjectProvider>
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
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/review-queue" element={<ReviewQueue />} />
          <Route path="/setup" element={<OnboardingPage />} />
          <Route path="/project" element={<ProjectOverview />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  )
}
