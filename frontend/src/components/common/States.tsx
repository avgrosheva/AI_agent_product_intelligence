import type { ReactNode } from 'react'
import { ApiError } from '../../api/client'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      {label}
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
 * before exposing it) so every existing call site keeps working. */
export function ErrorState({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return (
        <div className="state-box error" role="alert">
          Access denied — {error.detail}
        </div>
      )
    }
    if (error.status === 404) {
      return (
        <div className="state-box error" role="alert">
          Not found — {error.detail}
        </div>
      )
    }
    return (
      <div className="state-box error" role="alert">
        Request failed — {error.detail}
      </div>
    )
  }
  const message = typeof error === 'string' ? error : error instanceof Error ? error.message : 'Unknown error'
  return (
    <div className="state-box error" role="alert">
      Something went wrong: {message}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state-box">{children}</div>
}
