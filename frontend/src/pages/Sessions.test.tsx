import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import { Sessions } from './Sessions'
import { renderWithProviders } from '../test/renderWithProviders'
import { DOMAIN, EXPERIMENT_ID, GENERIC_SESSION_LIST_FIXTURE, apiGetMockImpl } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiGet: vi.fn() }
})

const LONG_TIMEOUT = { timeout: 3000 }
const SESSIONS_PATH = `/api/v1/domains/${DOMAIN}/sessions`

describe('Sessions page', () => {
  beforeEach(async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(apiGetMockImpl)
  })

  afterEach(() => {
    cleanup()
  })

  it('renders sessions returned by the backend and reflects a configured segment dimension from the URL as a selected dropdown value', async () => {
    renderWithProviders(<Sessions />, { route: `/sessions?experiment_id=${EXPERIMENT_ID}&platform=android` })
    await waitFor(() => expect(screen.getByText(/1 sessions match/)).toBeInTheDocument(), LONG_TIMEOUT)
    expect(screen.getByText('sess-000…')).toBeInTheDocument()
    // "platform" is a known dimension (SEGMENT_DIMENSIONS_FIXTURE), so it
    // renders as a labeled dropdown pre-selected to "android", not a
    // generic key:value chip (Stage 17 task 3).
    expect(await screen.findByRole('combobox', { name: 'platform' })).toHaveValue('android')
  })

  it('shows the detected-mechanism column and review-status chip once this domain has registered mechanisms', async () => {
    renderWithProviders(<Sessions />, { route: `/sessions?experiment_id=${EXPERIMENT_ID}` })
    await waitFor(() => expect(screen.getByText(/1 sessions match/)).toBeInTheDocument(), LONG_TIMEOUT)
    expect(screen.getByRole('columnheader', { name: 'Mechanisms' })).toBeInTheDocument()
    expect(screen.getByText('unnecessary_clarification')).toBeInTheDocument()
    expect(screen.getByText('unreviewed')).toBeInTheDocument()
  })

  it('forwards an unrecognized query param to the backend without rendering it as a structured control', async () => {
    const client = await import('../api/client')
    const calls: Record<string, string | number | undefined>[] = []
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === SESSIONS_PATH) calls.push(params ?? {})
      return apiGetMockImpl(path, params)
    })
    renderWithProviders(<Sessions />, { route: `/sessions?experiment_id=${EXPERIMENT_ID}&locale=en-US` })
    await waitFor(() => expect(calls.some((p) => p.locale === 'en-US')).toBe(true), LONG_TIMEOUT)
  })

  it('shows an empty state when no sessions match', async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === SESSIONS_PATH) return { ...GENERIC_SESSION_LIST_FIXTURE, items: [], total: 0 }
      return apiGetMockImpl(path, params)
    })
    renderWithProviders(<Sessions />, { route: '/sessions' })
    await waitFor(() => expect(screen.getByText('No sessions match these filters.')).toBeInTheDocument(), LONG_TIMEOUT)
  })

  it('shows an error state when the backend request fails', async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === SESSIONS_PATH) throw new Error('Internal Server Error')
      return apiGetMockImpl(path, params)
    })
    renderWithProviders(<Sessions />, { route: '/sessions' })
    await waitFor(() => expect(screen.getByText(/Internal Server Error/)).toBeInTheDocument(), LONG_TIMEOUT)
  })
})
