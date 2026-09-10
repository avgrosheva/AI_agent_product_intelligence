import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setToken } from '../api/client'
import { ActiveExperimentProvider } from '../state/ActiveExperimentContext'
import { AuthProvider } from '../state/AuthContext'

/** `path` is the route *pattern* (e.g. "/experiments/:experimentId") so
 * components using useParams() resolve correctly; `route` is the actual
 * URL to navigate to. Defaults to an exact match when a page takes no
 * params.
 *
 * Stage 14: every test tree is pre-authenticated (a fake token) so
 * existing page-level tests — written before the backend required auth
 * — never hit the login redirect; only App.test.tsx's routing tests
 * actually exercise RequireAuth, and they expect to see the app, not a
 * login form. Every test file that mocks ../api/client must preserve
 * its real getToken/setToken/clearToken/apiPost via vi.importActual —
 * see any existing *.test.tsx for the pattern — since AuthProvider
 * calls the real ones underneath. */
export function renderWithProviders(ui: ReactElement, { route = '/', path }: { route?: string; path?: string } = {}) {
  setToken('test-token')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const routePattern = path ?? route.split('?')[0]
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <ActiveExperimentProvider>
            <Routes>
              <Route path={routePattern} element={ui} />
            </Routes>
          </ActiveExperimentProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
