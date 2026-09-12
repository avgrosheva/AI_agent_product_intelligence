import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { SessionDetail } from './SessionDetail'
import { renderWithProviders } from '../test/renderWithProviders'
import { GENERIC_SESSION_DETAIL_FIXTURE } from '../test/fixtures'

// Stage 21: a fresh object each time (never a mutated GENERIC_SESSION_DETAIL_FIXTURE
// in place) -- TanStack Query's structural sharing treats an unchanged
// object reference as "no update" and skips re-rendering subscribers, so
// mutating the shared fixture in place would make a real confirm/reject
// silently invisible to this test even though the mutation itself succeeded.
let currentSession = GENERIC_SESSION_DETAIL_FIXTURE

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { apiGetMockImpl } = await import('../test/fixtures')
  const apiGet = vi.fn(async (path: string, params?: Record<string, string | number | undefined>) => {
    if (path === `/api/v1/domains/${GENERIC_SESSION_DETAIL_FIXTURE.domain}/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}`) return currentSession
    return apiGetMockImpl(path, params)
  })
  const apiPost = vi.fn(async (path: string, body: unknown) => {
    const failureMode = currentSession.failure_attributions[0].failure_mode
    if (path === `/api/v1/domains/${GENERIC_SESSION_DETAIL_FIXTURE.domain}/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}/attributions/${failureMode}/review`) {
      currentSession = {
        ...currentSession,
        failure_attributions: [
          { ...currentSession.failure_attributions[0], review_status: 'confirmed', reviewer: 'demo@example.com', reviewed_at: '2026-06-01T00:00:00Z' },
        ],
      }
      return { review_id: 'r1', domain: currentSession.domain, session_id: currentSession.session_id, failure_mode: failureMode, ...(body as object), created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z' }
    }
    throw new Error(`Unmocked POST path in test: ${path}`)
  })
  return { ...actual, apiGet, apiPost }
})

describe('SessionDetail page', () => {
  it('renders the transcript, action sequence, tool calls, and failure classification', async () => {
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}`,
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
      route: `/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })

    expect(await screen.findByText(/Deterministic mock classifier/i)).toBeInTheDocument()
    expect(screen.getByText(/not real LLM classification quality/i)).toBeInTheDocument()
  })

  it('does not render chain-of-thought — only observable action types', async () => {
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })
    await waitFor(() => expect(screen.getByText('search_products')).toBeInTheDocument())
    expect(screen.queryByText(/reasoning/i)).not.toBeInTheDocument()
  })

  it('lets a reviewer confirm an unreviewed attribution without leaving the session', async () => {
    currentSession = {
      ...GENERIC_SESSION_DETAIL_FIXTURE,
      failure_attributions: [{ ...GENERIC_SESSION_DETAIL_FIXTURE.failure_attributions[0], review_status: 'unreviewed', reviewer: null, reviewed_at: null }],
    }
    renderWithProviders(<SessionDetail />, {
      route: `/sessions/${GENERIC_SESSION_DETAIL_FIXTURE.session_id}`,
      path: '/sessions/:sessionId',
    })

    const confirmButton = await screen.findByRole('button', { name: 'Confirm' })
    confirmButton.click()

    await waitFor(() => expect(screen.getByText('confirmed')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })
})
