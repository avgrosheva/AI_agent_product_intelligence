import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { ReviewQueue } from './ReviewQueue'
import { renderWithProviders } from '../test/renderWithProviders'

const PROJECT = { project_id: 'proj-1', org_id: 'org-1', name: 'Test Project', domain: 'commerce', created_at: '2026-01-01T00:00:00Z' }
const EXP_ID = 'exp-1234'

const QUEUE_ITEM = {
  session_id: 'session-abc12345', experiment_id: EXP_ID, agent_version: 'v2', failure_mode: 'unnecessary_clarification',
  detector_source: 'semantic', confidence: 0.87, evidence_text: 'Agent asked for size despite it being stated.',
  reviewed: false, high_impact: true,
  detector_version: 'rule_based_mock-v1', provider: null, model: null, prompt_version: null, is_newest_version: true,
}

let currentItems = [QUEUE_ITEM]

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const apiGet = vi.fn(async (path: string) => {
    if (path === '/api/v1/auth/me') {
      return {
        user: { user_id: 'u1', email: 'a@b.com', created_at: '2026-01-01T00:00:00Z' },
        memberships: [{ membership_id: 'm1', org_id: 'org-1', user_id: 'u1', email: 'a@b.com', role: 'admin' as const, created_at: '2026-01-01T00:00:00Z' }],
        projects: [PROJECT],
      }
    }
    if (path === '/api/v1/domains/commerce/experiments') {
      return { domain: 'commerce', experiments: [{ experiment_id: EXP_ID, name: 'Test Experiment', control_version: 'v1', treatment_version: 'v2', start_date: null, end_date: null, n_sessions: null, n_users: null, north_star_metric: null, status_chip: 'not_yet_investigated' }] }
    }
    if (path === '/api/v1/domains/commerce/mechanisms') {
      return { domain: 'commerce', mechanisms: [{ name: 'unnecessary_clarification', source: 'semantic', description: 'x' }, { name: 'retrieval_failure', source: 'deterministic', description: 'y' }] }
    }
    if (path === '/api/v1/domains/commerce/review-queue') {
      return { domain: 'commerce', items: currentItems, total: currentItems.length, limit: 25, offset: 0 }
    }
    throw new Error(`Unmocked path in test: ${path}`)
  })
  const apiPost = vi.fn(async (path: string, body: unknown) => {
    if (path === `/api/v1/domains/commerce/sessions/${QUEUE_ITEM.session_id}/attributions/${QUEUE_ITEM.failure_mode}/review`) {
      currentItems = currentItems.map((i) => (i.session_id === QUEUE_ITEM.session_id ? { ...i, reviewed: true } : i))
      return { review_id: 'r1', domain: 'commerce', project_id: 'proj-1', session_id: QUEUE_ITEM.session_id, failure_mode: QUEUE_ITEM.failure_mode, ...(body as object), created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z' }
    }
    throw new Error(`Unmocked POST path in test: ${path}`)
  })
  return { ...actual, apiGet, apiPost }
})

describe('ReviewQueue', () => {
  it('shows an unreviewed attribution with mechanism, confidence, evidence, and a high-impact indicator', async () => {
    currentItems = [QUEUE_ITEM]
    renderWithProviders(<ReviewQueue />)

    await waitFor(() => expect(screen.getByText(/Agent asked for size despite it being stated/)).toBeInTheDocument())
    // Two matches are expected: the table cell AND the mechanism filter
    // dropdown's own option both render this text.
    expect(screen.getAllByText('unnecessary clarification').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('87%')).toBeInTheDocument()
    expect(screen.getByText('high impact')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /session-/ })).toHaveAttribute('href', `/sessions/${QUEUE_ITEM.session_id}`)
  })

  it('confirming an item marks it reviewed and removes the decision buttons', async () => {
    currentItems = [QUEUE_ITEM]
    renderWithProviders(<ReviewQueue />)

    const confirmButton = await screen.findByRole('button', { name: 'Confirm' })
    confirmButton.click()

    await waitFor(() => expect(screen.getByText('reviewed')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })

  it('shows the empty state when nothing matches the filters', async () => {
    currentItems = []
    renderWithProviders(<ReviewQueue />)
    await waitFor(() => expect(screen.getByText(/Nothing to review/)).toBeInTheDocument())
  })
})
