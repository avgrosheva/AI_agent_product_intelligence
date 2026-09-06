import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ActiveExperimentProvider } from '../state/ActiveExperimentContext'

/** `path` is the route *pattern* (e.g. "/experiments/:experimentId") so
 * components using useParams() resolve correctly; `route` is the actual
 * URL to navigate to. Defaults to an exact match when a page takes no
 * params. */
export function renderWithProviders(ui: ReactElement, { route = '/', path }: { route?: string; path?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const routePattern = path ?? route.split('?')[0]
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <ActiveExperimentProvider>
          <Routes>
            <Route path={routePattern} element={ui} />
          </Routes>
        </ActiveExperimentProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
