import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import { Sessions } from './Sessions'
import { renderWithProviders } from '../test/renderWithProviders'
import { EXPERIMENT_ID, SESSION_LIST_FIXTURE, apiGetMockImpl } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiGet: vi.fn() }
})

const LONG_TIMEOUT = { timeout: 3000 }

describe('Sessions page', () => {
  beforeEach(async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(apiGetMockImpl)
  })

  afterEach(() => {
    cleanup()
  })

  it('renders sessions returned by the backend and reflects filters from the URL', async () => {
    renderWithProviders(<Sessions />, { route: `/sessions?experiment_id=${EXPERIMENT_ID}&constraint_count_bucket=3%2B` })
    await waitFor(() => expect(screen.getByText(/1 sessions match/)).toBeInTheDocument(), LONG_TIMEOUT)
    expect(screen.getByText(/monitor, 3\+ constraints/)).toBeInTheDocument()
  })

  it('shows an empty state when no sessions match', async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === '/sessions') return { ...SESSION_LIST_FIXTURE, items: [], total: 0 }
      return apiGetMockImpl(path, params)
    })
    renderWithProviders(<Sessions />, { route: '/sessions' })
    await waitFor(() => expect(screen.getByText('No sessions match these filters.')).toBeInTheDocument(), LONG_TIMEOUT)
  })

  it('shows an error state when the backend request fails', async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === '/sessions') throw new Error('Internal Server Error')
      return apiGetMockImpl(path, params)
    })
    renderWithProviders(<Sessions />, { route: '/sessions' })
    await waitFor(() => expect(screen.getByText(/Internal Server Error/)).toBeInTheDocument(), LONG_TIMEOUT)
  })
})
