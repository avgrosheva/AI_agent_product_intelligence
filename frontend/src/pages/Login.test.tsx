import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Login } from './Login'
import { AuthProvider } from '../state/AuthContext'
import { clearToken } from '../api/client'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiPost: vi.fn() }
})

describe('Login', () => {
  it('submits email/password and stores the returned token on success', async () => {
    clearToken()
    const { apiPost } = await import('../api/client')
    vi.mocked(apiPost).mockResolvedValueOnce({ access_token: 'fresh-token', token_type: 'bearer' })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'demo@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/login', { email: 'demo@example.com', password: 'secret123' }))
  })

  it('shows an error message when login fails', async () => {
    clearToken()
    const { apiPost, ApiError } = await import('../api/client')
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(401, 'invalid email or password'))

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'demo@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText('invalid email or password')).toBeInTheDocument())
  })
})
