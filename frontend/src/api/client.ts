// Thin fetch wrapper. No analytics logic lives here or anywhere else in
// the frontend (PRD.md / Stage 6 brief SS12) — this module only calls the
// FastAPI backend and returns its JSON, typed.

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8123'
export const TOKEN_STORAGE_KEY = 'aipi_access_token'
export const REFRESH_TOKEN_STORAGE_KEY = 'aipi_refresh_token'

// Stage 14: the backend has required a bearer token since Stage 7; this
// frontend predates that and never sent one. getToken/setToken/clearToken
// are the minimal plumbing needed for ANY page (existing or new) to work
// against the current backend — not a new feature, a fix to a real gap.
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    // localStorage unavailable (e.g. private browsing) -- the session
    // simply won't persist across reloads; not fatal.
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // ignore
  }
}

// Stage 18 task 4: the access token this pairs with is now short-lived
// (15 minutes, was 24 hours) -- a caller that never refreshed it would
// get logged out mid-session every 15 minutes, a real regression from
// the caller's point of view even though nothing about auth itself
// broke. getRefreshToken/setRefreshToken/clearRefreshToken store the
// long-lived, revocable counterpart; authorizedFetch below is what
// actually spends it, transparently, the moment a request meets an
// expired access token.
export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setRefreshToken(token: string): void {
  try {
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token)
  } catch {
    // ignore
  }
}

export function clearRefreshToken(): void {
  try {
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY)
  } catch {
    // ignore
  }
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Stage 18 task 4: at most one refresh in flight at a time -- several
// requests can all discover their access token is expired within the
// same instant (e.g. a page that fires 4 queries on mount), and without
// this they'd each spend the one refresh token independently. Refresh
// tokens are single-use (rotation), so only the FIRST of those attempts
// may actually succeed; every concurrent caller instead awaits this one
// shared promise and reuses whatever it resolves to.
let refreshInFlight: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) throw new ApiError(401, 'No refresh token available')
    const res = await fetch(new URL('/api/v1/auth/refresh', BASE_URL).toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) {
      clearToken()
      clearRefreshToken()
      throw new ApiError(401, 'Session expired')
    }
    const body = (await res.json()) as { access_token: string; refresh_token: string }
    setToken(body.access_token)
    setRefreshToken(body.refresh_token)
    return body.access_token
  })()
  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // response wasn't JSON; fall back to statusText
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

// Stage 18 task 4: every GET/POST/PUT below routes through this so a
// 401 (expired access token — the ordinary, expected case at a 15-minute
// TTL, not a sign of anything wrong) transparently refreshes and retries
// ONCE rather than surfacing as a broken request or forcing the caller
// to re-login. A second 401 after a successful refresh means the
// resource itself denies this user regardless of token freshness, so it
// is not retried again. A refresh that itself fails (no refresh token,
// or it's expired/revoked) propagates as the original 401 — the caller
// is genuinely logged out, and RequireAuth's existing redirect-to-login
// handles that exactly as it always has.
async function authorizedFetch(url: string, init: RequestInit): Promise<Response> {
  const res = await fetch(url, { ...init, headers: { ...init.headers, ...authHeaders() } })
  if (res.status !== 401 || !getRefreshToken()) return res
  try {
    await refreshAccessToken()
  } catch {
    return res
  }
  return fetch(url, { ...init, headers: { ...init.headers, ...authHeaders() } })
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await authorizedFetch(url.toString(), {})
  return handleResponse<T>(res)
}

export async function apiPost<T>(path: string, body?: unknown, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await authorizedFetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}

export async function apiPut<T>(path: string, body?: unknown, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await authorizedFetch(url.toString(), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}
