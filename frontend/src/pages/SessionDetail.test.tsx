import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { SessionDetail } from './SessionDetail'
import { renderWithProviders } from '../test/renderWithProviders'
import { SESSION_DETAIL_FIXTURE } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { apiGet: vi.fn(apiGetMockImpl) }
})

describe('SessionDetail page', () => {
  it('renders the timeline, recommendations, evaluations, and failure classification', async () => {
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })

    await waitFor(() => expect(screen.getByText(/I need a monitor under \$300/)).toBeInTheDocument())
    expect(screen.getByText(/Could you clarify your preferred screen size/)).toBeInTheDocument()
    expect(screen.getByText('search_products')).toBeInTheDocument()
    expect(screen.getByText('Detected failure mechanisms')).toBeInTheDocument()
    expect(screen.getByText('unnecessary clarification')).toBeInTheDocument()
  })

  it('shows classifier provenance / mock disclaimer for a mock-classified session', async () => {
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })

    expect(await screen.findByText(/Deterministic mock classifier/i)).toBeInTheDocument()
    expect(screen.getByText(/not real LLM classification quality/i)).toBeInTheDocument()
  })

  it('does not render chain-of-thought — only observable action types', async () => {
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })
    await waitFor(() => expect(screen.getByText('search_products')).toBeInTheDocument())
    expect(screen.queryByText(/reasoning/i)).not.toBeInTheDocument()
  })
})
