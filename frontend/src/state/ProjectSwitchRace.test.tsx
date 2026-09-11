import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { renderWithProviders } from '../test/renderWithProviders'

// Stage 17 task 1 regression test: switching the active project must
// never send a request pairing the OLD project's experiment id with the
// NEW project's domain/project_id. This was possible before the fix
// because ActiveExperimentContext kept activeExperimentId in its own
// useState, reset by a useEffect that runs one render after domain/
// projectId already switched -- see ActiveExperimentContext.tsx's own
// docstring for the mechanism.

const PROJECT_A = { project_id: 'proj-a', org_id: 'org-1', name: 'Project A', domain: 'commerce', created_at: '2026-01-01T00:00:00Z' }
const PROJECT_B = { project_id: 'proj-b', org_id: 'org-1', name: 'Project B', domain: 'commerce', created_at: '2026-01-01T00:00:00Z' }
const EXP_A = { experiment_id: 'exp-a', name: 'Experiment A', control_version: 'v1', treatment_version: 'v2', start_date: null, end_date: null, n_sessions: null, n_users: null, north_star_metric: null, status_chip: 'not_yet_investigated' as const }
const EXP_B = { experiment_id: 'exp-b', name: 'Experiment B', control_version: 'v1', treatment_version: 'v2', start_date: null, end_date: null, n_sessions: null, n_users: null, north_star_metric: null, status_chip: 'not_yet_investigated' as const }

const mismatches: string[] = []
const requestLog: string[] = []

function apiGetMock(path: string, params?: Record<string, string | number | undefined>): Promise<unknown> {
  requestLog.push(`${path}?${JSON.stringify(params ?? {})}`)

  if (path === '/api/v1/auth/me') {
    return Promise.resolve({
      user: { user_id: 'u1', email: 'a@b.com', created_at: '2026-01-01T00:00:00Z' },
      memberships: [{ membership_id: 'm1', org_id: 'org-1', user_id: 'u1', email: 'a@b.com', role: 'admin' as const, created_at: '2026-01-01T00:00:00Z' }],
      projects: [PROJECT_A, PROJECT_B],
    })
  }
  if (path === '/api/v1/domains/commerce/experiments') {
    const pid = params?.project_id
    if (pid === 'proj-a') return Promise.resolve({ domain: 'commerce', experiments: [EXP_A] })
    if (pid === 'proj-b') return Promise.resolve({ domain: 'commerce', experiments: [EXP_B] })
    return Promise.reject(new Error(`unexpected project_id in experiments list: ${pid}`))
  }
  const guardrailMatch = path.match(/^\/api\/v1\/domains\/commerce\/experiments\/([^/]+)\/guardrails$/)
  if (guardrailMatch) {
    const experimentIdInPath = guardrailMatch[1]
    const projectIdInParams = params?.project_id
    const belongsToA = projectIdInParams === 'proj-a' && experimentIdInPath === 'exp-a'
    const belongsToB = projectIdInParams === 'proj-b' && experimentIdInPath === 'exp-b'
    if (!belongsToA && !belongsToB) {
      mismatches.push(`guardrails request paired project_id=${projectIdInParams} with experiment_id=${experimentIdInPath}`)
    }
    return Promise.resolve({ domain: 'commerce', experiment_id: experimentIdInPath, checks: [], any_breach: false, any_warning_breach: false })
  }
  return Promise.reject(new Error(`Unmocked path in test: ${path}`))
}

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiGet: vi.fn(apiGetMock) }
})

describe('project switch race condition (Stage 17 task 1)', () => {
  it('never requests guardrails for an experiment that belongs to the previous project', async () => {
    renderWithProviders(<App />, { route: '/', path: '*' })

    // Land on Project A implicitly picked... no -- two projects means the
    // explicit picker shows first (Stage 16 task 1's own guarantee).
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Select a project' })).toBeInTheDocument())
    await userEvent.click(screen.getByText('Project A'))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Experiment A' })).toBeInTheDocument())

    // Switch to Project B via the sidebar switcher -- this is the exact
    // action that used to race.
    const switcher = screen.getByRole('combobox', { name: 'Switch active project' })
    await userEvent.selectOptions(switcher, 'proj-b')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Experiment B' })).toBeInTheDocument())

    expect(mismatches).toEqual([])
  })
})
