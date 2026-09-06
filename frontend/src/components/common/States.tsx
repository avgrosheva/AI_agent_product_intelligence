import type { ReactNode } from 'react'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      {label}
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-box error" role="alert">
      Something went wrong: {message}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state-box">{children}</div>
}
