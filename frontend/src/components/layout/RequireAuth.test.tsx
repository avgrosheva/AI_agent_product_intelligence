import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RequireAuth } from './RequireAuth'
import { AuthProvider } from '../../state/AuthContext'
import { clearToken } from '../../api/client'

function renderProtected(route: string) {
  clearToken()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login screen</div>} />
            <Route path="/welcome" element={<div>Landing screen</div>} />
            <Route path="/setup" element={<RequireAuth><div>Setup screen</div></RequireAuth>} />
            <Route path="/project" element={<RequireAuth><div>Overview screen</div></RequireAuth>} />
            <Route path="/" element={<RequireAuth><div>Root screen</div></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RequireAuth route protection', () => {
  it('redirects an unauthenticated visitor to /login instead of rendering the setup page', () => {
    renderProtected('/setup')
    expect(screen.getByText('Login screen')).toBeInTheDocument()
    expect(screen.queryByText('Setup screen')).not.toBeInTheDocument()
  })

  it('redirects an unauthenticated visitor away from the project overview page too', () => {
    renderProtected('/project')
    expect(screen.getByText('Login screen')).toBeInTheDocument()
    expect(screen.queryByText('Overview screen')).not.toBeInTheDocument()
  })

  it('sends an unauthenticated visit to the app root to the landing page, not the bare login form', () => {
    renderProtected('/')
    expect(screen.getByText('Landing screen')).toBeInTheDocument()
    expect(screen.queryByText('Root screen')).not.toBeInTheDocument()
    expect(screen.queryByText('Login screen')).not.toBeInTheDocument()
  })
})
