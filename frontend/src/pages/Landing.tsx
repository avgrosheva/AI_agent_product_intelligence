import { Link, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageToggle } from '../components/common/LanguageToggle'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useAuth } from '../state/AuthContext'

const FEATURE_KEYS = [
  { titleKey: 'landing.featureReleaseTitle', bodyKey: 'landing.featureReleaseBody', accent: 'var(--color-positive)' },
  { titleKey: 'landing.featureInvestigationTitle', bodyKey: 'landing.featureInvestigationBody', accent: 'var(--color-accent)' },
  { titleKey: 'landing.featureAIQualityTitle', bodyKey: 'landing.featureAIQualityBody', accent: 'var(--color-cyan)' },
  { titleKey: 'landing.featureReviewTitle', bodyKey: 'landing.featureReviewBody', accent: 'var(--color-warning)' },
] as const

/** Stage 20 follow-up: the one screen this app deliberately treats as a
 * marketing page rather than a product surface -- everywhere else,
 * "don't turn the screen into a landing page" holds; here, that's
 * literally the job. Public (outside RequireAuth); an already-signed-in
 * visitor is sent straight into the app rather than shown a pitch for a
 * product they're already using. */
export function Landing() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  if (isAuthenticated) return <Navigate to="/" replace />

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px', maxWidth: 1180, margin: '0 auto' }}>
        <div className="brand-mark">
          <span className="brand-glyph" aria-hidden="true" />
          <span className="sidebar-brand" style={{ fontSize: 15 }}>{t('landing.brand')}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <LanguageToggle />
          <ThemeToggle />
          <Link to="/login" className="btn btn-small">{t('auth.signIn')}</Link>
          <Link to="/register" className="btn btn-primary btn-small">{t('landing.getStarted')}</Link>
        </div>
      </header>

      <main className="page" style={{ maxWidth: 1180, gap: 56 }}>
        <section className="page-hero" style={{ padding: '64px 48px', textAlign: 'center' }}>
          <div className="deco deco-blob" aria-hidden="true" style={{ width: 260, height: 260, top: -90, left: -100, background: 'var(--color-accent)', opacity: 0.45 }} />
          <div className="deco deco-pixels" aria-hidden="true" style={{ width: 220, height: 220, bottom: -60, right: -40, color: 'var(--color-lime)' }} />
          <div className="deco deco-bar" aria-hidden="true" style={{ width: 140, height: 26, top: 36, right: 60, background: 'var(--color-cyan)' }} />
          <div className="page-hero-content" style={{ maxWidth: 720, margin: '0 auto' }}>
            <h1 style={{ fontSize: 52, lineHeight: 1.04, marginBottom: 18 }}>
              {t('landing.heroHeadline')}
            </h1>
            <p className="text-secondary" style={{ fontSize: 16.5, marginBottom: 28 }}>
              {t('landing.heroSub')}
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <Link to="/register" className="btn btn-primary" style={{ padding: '11px 22px', fontSize: 14 }}>
                {t('landing.getStartedFree')}
              </Link>
              <Link to="/login" className="btn" style={{ padding: '11px 22px', fontSize: 14 }}>
                {t('auth.signIn')}
              </Link>
            </div>
          </div>
        </section>

        <section>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div className="card-kicker" style={{ marginBottom: 8 }}>{t('landing.whatYouGet')}</div>
            <h2 style={{ fontSize: 26 }}>{t('landing.featuresHeading')}</h2>
          </div>
          <div className="grid-2" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 }}>
            {FEATURE_KEYS.map((f) => (
              <div className="card" key={f.titleKey}>
                <div aria-hidden="true" style={{ width: 34, height: 34, borderRadius: 10, background: f.accent, opacity: 0.16, marginBottom: 12 }} />
                <h3 style={{ marginBottom: 8, fontSize: 16 }}>{t(f.titleKey)}</h3>
                <p className="text-secondary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{t(f.bodyKey)}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="page-hero" style={{ padding: '40px 44px', textAlign: 'center', background: 'linear-gradient(135deg, var(--color-accent-weak) 0%, var(--color-bg) 100%)' }}>
          <div className="page-hero-content">
            <h2 style={{ fontSize: 24, marginBottom: 10 }}>{t('landing.ctaHeading')}</h2>
            <p className="text-secondary" style={{ marginBottom: 20 }}>{t('landing.ctaSub')}</p>
            <Link to="/register" className="btn btn-primary" style={{ padding: '11px 22px', fontSize: 14 }}>
              {t('landing.createYourAccount')}
            </Link>
          </div>
        </section>
      </main>

      <footer style={{ textAlign: 'center', padding: '28px 20px', color: 'var(--color-text-muted)', fontSize: 12 }}>
        {t('landing.brand')}
      </footer>
    </div>
  )
}
