import { describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from './AuthContext'
import { clearToken, getRefreshToken, setRefreshToken, setToken } from '../api/client'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiPost: vi.fn().mockResolvedValue({}) }
})

/** Stage 21: logging out on a shared browser must not leave the next
 * account to sign in able to see the previous account's cached data or
 * project selection -- react-query serves cached data instantly while a
 * fresh request is in flight, so a stale `['me']` cache entry or a
 * leftover `aipi.activeProjectId` from the last session briefly points
 * the new session at an account it doesn't belong to (observed as a
 * stray 403 to another org's project right after switching accounts). */
describe('AuthContext logout', () => {
  it('clears the query cache and every account-scoped localStorage key, but leaves device preferences alone', async () => {
    setToken('old-token')
    setRefreshToken('old-refresh')
    localStorage.setItem('aipi.activeProjectId', 'stale-project-id')
    localStorage.setItem('aipi.activeExperimentId.stale-project-id', 'stale-experiment-id')
    localStorage.setItem('theme', 'dark')
    localStorage.setItem('language', 'ru')

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(['me'], { user: { user_id: 'old-user' } })

    function wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <AuthProvider>{children}</AuthProvider>
        </QueryClientProvider>
      )
    }
    const { result } = renderHook(() => useAuth(), { wrapper })

    act(() => {
      result.current.logout()
    })

    expect(queryClient.getQueryData(['me'])).toBeUndefined()
    expect(localStorage.getItem('aipi.activeProjectId')).toBeNull()
    expect(localStorage.getItem('aipi.activeExperimentId.stale-project-id')).toBeNull()
    expect(getRefreshToken()).toBeNull()
    // Device-level preferences are not per-account and must survive logout.
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(localStorage.getItem('language')).toBe('ru')

    clearToken()
  })

  it('does not clear an active query subscriber into a permanently empty state before it can refetch', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <AuthProvider>{children}</AuthProvider>
        </QueryClientProvider>
      )
    }
    const { result } = renderHook(
      () => ({ auth: useAuth(), query: useQuery({ queryKey: ['me'], queryFn: () => Promise.resolve({ ok: true }) }) }),
      { wrapper },
    )

    await vi.waitFor(() => expect(result.current.query.data).toEqual({ ok: true }))

    act(() => {
      result.current.auth.logout()
    })

    // A logout that only clears the cache (never removes the query's own
    // subscribers) lets an already-mounted screen refetch on its own,
    // rather than getting stuck on stale data with no observer left to
    // trigger a refetch.
    await vi.waitFor(() => expect(result.current.query.data).toEqual({ ok: true }))
  })
})
