import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiPost, clearRefreshToken, clearToken, getRefreshToken, getToken, setRefreshToken, setToken } from '../api/client'

/** Stage 21: every project/experiment-selection key this app persists is
 * namespaced under this prefix (ActiveProjectContext's `aipi.activeProjectId`,
 * ActiveExperimentContext's `aipi.activeExperimentId.<projectId>`) -- unlike
 * the device-level `theme`/`language` keys, these describe what the
 * PREVIOUS account was looking at and must not leak into a different
 * account's first render after a login on the same browser. */
const ACCOUNT_SCOPED_STORAGE_PREFIX = 'aipi.'

function clearAccountScopedStorage() {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(ACCOUNT_SCOPED_STORAGE_PREFIX)) localStorage.removeItem(key)
    }
  } catch {
    // best-effort only
  }
}

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

interface AuthContextValue {
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const queryClient = useQueryClient()

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiPost<TokenResponse>('/api/v1/auth/login', { email, password })
    setToken(response.access_token)
    setRefreshToken(response.refresh_token)
    setTokenState(response.access_token)
  }, [])

  const logout = useCallback(() => {
    // Stage 18 task 4: revoke the refresh token server-side too, not just
    // forget it locally -- best-effort (fire-and-forget: a logout must
    // still clear the local session immediately even if this request
    // never lands, e.g. the user is offline). Without this, "logout"
    // would only ever be a client-side illusion; the refresh token
    // would stay valid until it naturally expired.
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      apiPost('/api/v1/auth/logout', { refresh_token: refreshToken }).catch(() => {
        // ignore -- local logout proceeds regardless
      })
    }
    clearToken()
    clearRefreshToken()
    setTokenState(null)
    // Stage 21: without this, a different account logging in right after
    // on the same browser briefly saw the PREVIOUS account's cached
    // `/auth/me` response and persisted project selection -- react-query
    // serves stale cache instantly while the fresh request is in flight,
    // so for one render the new session queried the old account's
    // project_id (observed as a stray 403 in the backend log right after
    // switching accounts).
    queryClient.clear()
    clearAccountScopedStorage()
  }, [queryClient])

  const value = useMemo(() => ({ isAuthenticated: token !== null, login, logout }), [token, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
