import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { apiPost, clearToken, getToken, setToken } from '../api/client'

interface TokenResponse {
  access_token: string
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

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiPost<TokenResponse>('/api/v1/auth/login', { email, password })
    setToken(response.access_token)
    setTokenState(response.access_token)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
  }, [])

  const value = useMemo(() => ({ isAuthenticated: token !== null, login, logout }), [token, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
