import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Alerts } from './Alerts'
import { renderWithProviders } from '../test/renderWithProviders'

const PROJECT = { project_id: 'proj-1', org_id: 'org-1', name: 'Test Project', domain: 'commerce', created_at: '2026-01-01T00:00:00Z' }
const EXP_ID = 'exp-1234'

const OPEN_ALERT = {
  alert_id: 'alert-1', domain: 'commerce', experiment_id: EXP_ID, evaluation_id: 'eval-1', rule: 'rollback' as const,
  severity: 'critical' as const, reason: 'abandonment_rate regressed significantly', related_guardrail: null, related_finding: null,
  status: 'open' as const, created_at: '2026-06-01T00:00:00Z', acknowledged_at: null,
}

// Mutated per-test (before render) rather than re-mocked per-test — a
// single top-level vi.mock is hoisted above imports, so re-declaring it
// per test isn't how vitest module mocking works; a shared, reassignable
// alert object is the simplest way to vary one field across tests.
let currentAlert = OPEN_ALERT

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
    if (path === '/api/v1/alerts') {
      return { alerts: [currentAlert], total: 1, limit: 25, offset: 0 }
    }
    throw new Error(`Unmocked path in test: ${path}`)
  })
  const apiPost = vi.fn(async (path: string) => {
    if (path === `/api/v1/alerts/${currentAlert.alert_id}/acknowledge`) {
      currentAlert = { ...currentAlert, status: 'acknowledged', acknowledged_at: '2026-06-01T01:00:00Z' }
      return currentAlert
    }
    throw new Error(`Unmocked POST path in test: ${path}`)
  })
  return { ...actual, apiGet, apiPost }
})

describe('Alerts', () => {
  it('shows an open alert with severity, rule, and an Acknowledge action', async () => {
    currentAlert = OPEN_ALERT
    renderWithProviders(<Alerts />)

    await waitFor(() => expect(screen.getByText(/abandonment_rate regressed significantly/)).toBeInTheDocument())
    expect(screen.getByText('critical')).toBeInTheDocument()
    expect(screen.getByText('open')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeInTheDocument()
  })

  it('does not show an Acknowledge action for an already-acknowledged alert', async () => {
    currentAlert = { ...OPEN_ALERT, status: 'acknowledged', acknowledged_at: '2026-06-01T01:00:00Z' }
    renderWithProviders(<Alerts />)

    await waitFor(() => expect(screen.getByText('acknowledged')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })

  it('acknowledging an open alert removes the Acknowledge action', async () => {
    currentAlert = OPEN_ALERT
    renderWithProviders(<Alerts />)

    const ackButton = await screen.findByRole('button', { name: 'Acknowledge' })
    ackButton.click()

    await waitFor(() => expect(screen.getByText('acknowledged')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })
})
