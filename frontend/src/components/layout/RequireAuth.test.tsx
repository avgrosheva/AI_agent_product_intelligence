import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './RequireAuth'
import { AuthProvider } from '../../state/AuthContext'
import { clearToken } from '../../api/client'

function renderProtected(route: string) {
  clearToken()
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login screen</div>} />
          <Route path="/setup" element={<RequireAuth><div>Setup screen</div></RequireAuth>} />
          <Route path="/project" element={<RequireAuth><div>Overview screen</div></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
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
})
