import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../state/AuthContext'

export function Login() {
  const { isAuthenticated, login } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? '/'
    return <Navigate to={from} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 360, margin: '80px auto' }}>
      <h1 style={{ marginBottom: 4 }}>Sign in</h1>
      <p className="text-secondary" style={{ marginBottom: 20 }}>AI Agent Product Intelligence</p>
      <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span className="text-muted" style={{ fontSize: 12 }}>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span className="text-muted" style={{ fontSize: 12 }}>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div className="chip chip-negative" style={{ alignSelf: 'flex-start' }}>{error}</div>}
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
