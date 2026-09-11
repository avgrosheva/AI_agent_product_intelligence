import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setToken } from '../api/client'
import { ActiveExperimentProvider } from '../state/ActiveExperimentContext'
import { ActiveProjectProvider } from '../state/ActiveProjectContext'
import { AuthProvider } from '../state/AuthContext'

/** `path` is the route *pattern* (e.g. "/experiments/:experimentId") so
 * components using useParams() resolve correctly; `route` is the actual
 * URL to navigate to. Defaults to an exact match when a page takes no
 * params.
 *
 * Stage 14: every test tree is pre-authenticated (a fake token) so
 * existing page-level tests — written before the backend required auth —
 * never hit the login redirect; only App.test.tsx's routing tests
 * actually exercise RequireAuth, and they expect to see the app, not a
 * login form. Every test file that mocks ../api/client must preserve its
 * real getToken/setToken/clearToken/apiPost via vi.importActual — see
 * any existing *.test.tsx for the pattern — since AuthProvider calls the
 * real ones underneath.
 *
 * Stage 16: also wraps ActiveProjectProvider (previously only present on
 * the onboarding/project routes) since every screen is now project/
 * domain-scoped. A test that mocks ../api/client via fixtures.ts's
 * apiGetMockImpl gets a one-project /api/v1/auth/me response for free,
 * so ActiveProjectContext auto-selects it exactly like a real
 * single-project account (RequireAuth.test.tsx and ProjectOverview.test.tsx
 * cover the multi-project / zero-project picker states explicitly). */
export function renderWithProviders(ui: ReactElement, { route = '/', path }: { route?: string; path?: string } = {}) {
  setToken('test-token')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const routePattern = path ?? route.split('?')[0]
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <ActiveProjectProvider>
            <ActiveExperimentProvider>
              <Routes>
                <Route path={routePattern} element={ui} />
              </Routes>
            </ActiveExperimentProvider>
          </ActiveProjectProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
