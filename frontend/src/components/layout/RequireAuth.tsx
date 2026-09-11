import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../state/AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) {
    // An unauthenticated visit to the app's own root reaches the
    // marketing landing page (where sign-in/registration live), not a
    // bare login form with no context; every other protected deep link
    // still bounces straight to /login as before.
    const target = location.pathname === '/' ? '/welcome' : '/login'
    return <Navigate to={target} state={{ from: location.pathname }} replace />
  }
  return <>{children}</>
}
