import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { ProjectOverview } from './ProjectOverview'
import { ActiveProjectProvider } from '../state/ActiveProjectContext'
import { renderWithProviders } from '../test/renderWithProviders'

const PROJECT = { project_id: 'proj-1', org_id: 'org-1', name: 'Test Project', domain: 'commerce', created_at: '2026-01-01T00:00:00Z' }

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
    // Every project-scoped query except monitoring/configs "succeeds"
    // with a minimal, valid empty-ish shape; monitoring is the one that
    // fails, to prove one failed card doesn't sink the whole page or
    // hang forever as "Loading…" (Stage 17 task 4).
    if (path === '/api/v1/domains/commerce/onboarding-status') {
      return { project_id: 'proj-1', domain: 'commerce', ingestion_connected: true, data_received: true, primary_metric_configured: true, guardrails_configured: true, data_quality_status: 'healthy', monitoring_enabled: false, notifications_configured: false }
    }
    if (path === '/api/v1/domains/commerce/data-quality') {
      return { project_id: 'proj-1', domain: 'commerce', status: 'healthy', generated_at: '2026-01-01T00:00:00Z', checks: [] }
    }
    if (path === '/api/v1/domains/commerce/config') {
      return { project_id: 'proj-1', primary_metric: null, metrics: null, guardrails: null, segment_dimensions: null, economics: null, monitoring_cadence_seconds: null, enabled_notification_rules: [], created_at: null, updated_at: null, available_metrics: [], available_guardrails: [], available_context_fields: [] }
    }
    if (path === '/api/v1/domains/commerce/experiments') {
      return { domain: 'commerce', experiments: [] }
    }
    if (path === '/api/v1/monitoring/configs') {
      throw new actual.ApiError(403, "You are not authorized to view this project's monitoring configuration")
    }
    if (path === '/api/v1/notifications/channels') {
      return { channels: [] }
    }
    throw new Error(`Unmocked path in test: ${path}`)
  })
  return { ...actual, apiGet }
})

describe('ProjectOverview error handling (Stage 17 task 4)', () => {
  it('shows Access denied on the Monitoring card instead of hanging on Loading… when that one request fails', async () => {
    renderWithProviders(
      <ActiveProjectProvider>
        <ProjectOverview />
      </ActiveProjectProvider>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Test Project' })).toBeInTheDocument())
    // The other cards still resolve normally even though Monitoring failed.
    await waitFor(() => expect(screen.getByText('healthy')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/Access denied/)).toBeInTheDocument())
    expect(screen.queryByText('Not scheduled')).not.toBeInTheDocument()
  })
})
