import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../api/client'

export function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="state-box" role="status" aria-live="polite">
      <div className="skeleton-stack" aria-hidden="true">
        <div className="skeleton-bar" />
        <div className="skeleton-bar" />
      </div>
      {label ?? t('common.loading')}
    </div>
  )
}

/** Stage 17 task 4: distinguishes access-denied (401/403) and not-found
 * (404) from a generic request failure, instead of every error rendering
 * as the same "Something went wrong" -- and always shows the backend's
 * own `detail` text (already a plain sentence, never a stack trace) for
 * an ApiError, rather than a raw fetch/JS error message. Accepts the raw
 * thrown value (usually an ApiError, from any useDomainX hook's `error`)
 * or a plain string (a couple of contexts stringify their own error
 * before exposing it) so every existing call site keeps working. The
 * backend's own `detail` text is never translated -- it's real
 * diagnostic content, not app chrome. */
export function ErrorState({ error }: { error: unknown }) {
  const { t } = useTranslation()
  const icon = <div className="state-icon error" aria-hidden="true" />
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return (
        <div className="state-box error" role="alert">
          {icon}
          {t('states.accessDenied')} — {error.detail}
        </div>
      )
    }
    if (error.status === 404) {
      return (
        <div className="state-box error" role="alert">
          {icon}
          {t('states.notFound')} — {error.detail}
        </div>
      )
    }
    return (
      <div className="state-box error" role="alert">
        {icon}
        {t('states.requestFailed')} — {error.detail}
      </div>
    )
  }
  const message = typeof error === 'string' ? error : error instanceof Error ? error.message : 'Unknown error'
  return (
    <div className="state-box error" role="alert">
      {icon}
      {t('states.somethingWentWrong')}: {message}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="state-box">
      <div className="state-icon empty" aria-hidden="true" />
      {children}
    </div>
  )
}
