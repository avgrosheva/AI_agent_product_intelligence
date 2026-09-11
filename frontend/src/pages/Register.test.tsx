import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Register } from './Register'
import { AuthProvider } from '../state/AuthContext'
import { LanguageProvider } from '../state/LanguageContext'
import { ThemeProvider } from '../state/ThemeContext'
import { clearToken } from '../api/client'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiPost: vi.fn() }
})

function renderRegister() {
  return render(
    <ThemeProvider>
      <LanguageProvider>
        <MemoryRouter initialEntries={['/register']}>
          <AuthProvider>
            <Register />
          </AuthProvider>
        </MemoryRouter>
      </LanguageProvider>
    </ThemeProvider>,
  )
}

describe('Register', () => {
  it('registers then immediately signs in with the same credentials, in that order', async () => {
    clearToken()
    const { apiPost } = await import('../api/client')
    vi.mocked(apiPost).mockImplementation(async (path: string) => {
      if (path === '/api/v1/auth/register') return { user_id: 'u1', email: 'new@example.com', created_at: '2026-01-01T00:00:00Z' }
      if (path === '/api/v1/auth/login') return { access_token: 'fresh-token', refresh_token: 'fresh-refresh', token_type: 'bearer' }
      throw new Error(`Unmocked path: ${path}`)
    })

    renderRegister()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'longenoughpass' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'longenoughpass' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/register', { email: 'new@example.com', password: 'longenoughpass' }),
    )
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/login', { email: 'new@example.com', password: 'longenoughpass' }),
    )
    const registerCallOrder = vi.mocked(apiPost).mock.calls.findIndex((c) => c[0] === '/api/v1/auth/register')
    const loginCallOrder = vi.mocked(apiPost).mock.calls.findIndex((c) => c[0] === '/api/v1/auth/login')
    expect(registerCallOrder).toBeLessThan(loginCallOrder)
  })

  it('rejects mismatched passwords before ever calling the API', async () => {
    clearToken()
    const { apiPost } = await import('../api/client')
    vi.mocked(apiPost).mockClear()

    renderRegister()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'longenoughpass' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'somethingelse' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(screen.getByText('Passwords do not match.')).toBeInTheDocument())
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('shows the backend error for an already-registered email and does not attempt login', async () => {
    clearToken()
    const { apiPost, ApiError } = await import('../api/client')
    vi.mocked(apiPost).mockReset()
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(409, "'taken@example.com' is already registered"))

    renderRegister()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'taken@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'longenoughpass' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'longenoughpass' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(screen.getByText("'taken@example.com' is already registered")).toBeInTheDocument())
    expect(apiPost).toHaveBeenCalledTimes(1)
  })
})
