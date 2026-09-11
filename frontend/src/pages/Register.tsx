import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { apiPost, ApiError } from '../api/client'
import { LanguageToggle } from '../components/common/LanguageToggle'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useAuth } from '../state/AuthContext'

const MIN_PASSWORD_LENGTH = 8

/** Registers a new platform user, then immediately signs them in (same
 * credentials) so they land straight in the app rather than being
 * bounced back to a separate login step -- a brand-new user has no
 * organization or project yet, so AppLayout's own NoProjectPrompt/
 * ProjectStep (Stage 15) already carries them through creating both;
 * this page's only job is turning up with a valid session. */
export function Register() {
  const { t } = useTranslation()
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(t('auth.passwordTooShort', { count: MIN_PASSWORD_LENGTH }))
      return
    }
    if (password !== confirmPassword) {
      setError(t('auth.passwordsDoNotMatch'))
      return
    }
    setSubmitting(true)
    try {
      await apiPost('/api/v1/auth/register', { email, password })
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t('auth.registrationFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 960, margin: '0 auto', minHeight: '100vh', justifyContent: 'center' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="page-hero" style={{ padding: '48px 44px', display: 'grid', gridTemplateColumns: '1fr 360px', gap: 40, alignItems: 'center' }}>
        <div className="deco deco-blob" aria-hidden="true" style={{ width: 240, height: 240, top: -80, left: -90, background: 'var(--color-cyan)', opacity: 0.5 }} />
        <div className="deco deco-pixels" aria-hidden="true" style={{ width: 200, height: 200, bottom: -60, left: '38%', color: 'var(--color-lime)' }} />
        <div className="deco deco-bar" aria-hidden="true" style={{ width: 130, height: 24, bottom: 30, right: 16, background: 'var(--color-accent)' }} />

        <div className="page-hero-content">
          <span className="brand-glyph" aria-hidden="true" style={{ marginBottom: 16, display: 'inline-block' }} />
          <h1 style={{ fontSize: 42, marginBottom: 12 }}>
            {t('auth.registerHeroHeadline').split('\n').map((line, i, arr) => (
              <span key={i}>{line}{i < arr.length - 1 && <br />}</span>
            ))}
          </h1>
          <p className="text-secondary" style={{ maxWidth: 380, fontSize: 14.5 }}>
            {t('auth.registerHeroSub')}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card page-hero-content" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <h2 style={{ marginBottom: 2 }}>{t('auth.createYourAccount')}</h2>
          <p className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>{t('auth.freeToStart')}</p>
          <label className="field">
            <span>{t('auth.email')}</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </label>
          <label className="field">
            <span>{t('auth.password')}</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} />
          </label>
          <label className="field">
            <span>{t('auth.confirmPassword')}</span>
            <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} />
          </label>
          {error && <div className="chip chip-negative" style={{ alignSelf: 'flex-start' }}>{error}</div>}
          <button type="submit" className="btn btn-primary" disabled={submitting} style={{ justifyContent: 'center', marginTop: 4 }}>
            {submitting ? t('auth.creatingAccount') : t('auth.createAccount')}
          </button>
          <p className="text-muted" style={{ fontSize: 12, textAlign: 'center', marginTop: 4 }}>
            {t('auth.alreadyHaveAccount')} <Link to="/login" style={{ color: 'var(--color-accent-strong)', fontWeight: 600 }}>{t('auth.signIn')}</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
