// Thin fetch wrapper. No analytics logic lives here or anywhere else in
// the frontend (PRD.md / Stage 6 brief SS12) — this module only calls the
// FastAPI backend and returns its JSON, typed.

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8123'
export const TOKEN_STORAGE_KEY = 'aipi_access_token'

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

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), { headers: authHeaders() })
  return handleResponse<T>(res)
}

export async function apiPost<T>(path: string, body?: unknown, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
  const res = await fetch(url.toString(), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}
