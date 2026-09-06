// Thin fetch wrapper. No analytics logic lives here or anywhere else in
// the frontend (PRD.md / Stage 6 brief SS12) — this module only calls the
// FastAPI backend and returns its JSON, typed.

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8123'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString())
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
