import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { ProjectOverview } from './ProjectOverview'
import { ActiveProjectProvider } from '../state/ActiveProjectContext'
import { renderWithProviders } from '../test/renderWithProviders'
import { resetOnboardingMocks, server } from '../test/onboardingFixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { createOnboardingApiMocks } = await import('../test/onboardingFixtures')
  const { apiGet, apiPut, apiPost } = createOnboardingApiMocks(actual.ApiError)
  return { ...actual, apiGet, apiPut, apiPost }
})

function renderOverview() {
  return renderWithProviders(
    <ActiveProjectProvider>
      <ProjectOverview />
    </ActiveProjectProvider>,
  )
}

beforeEach(() => {
  resetOnboardingMocks()
})

describe('ProjectOverview', () => {
  it('shows readiness, data quality, connector, monitoring, and notification status for the active project', async () => {
    renderOverview()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Test Support Project' })).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('2 blocking issue(s)')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('healthy')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Connected')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Not scheduled')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('0 channel(s), 0 event type(s)')).toBeInTheDocument())
  })

  it('lists experiments with a not-yet-evaluated release status when none has run', async () => {
    renderOverview()
    await waitFor(() => expect(screen.getByText('Support Bot Rollout')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Not yet evaluated')).toBeInTheDocument())
  })

  it('shows a prompt to finish setup when no project is selected yet', async () => {
    server.me = { user: server.me.user, memberships: [], projects: [] }
    renderOverview()
    await waitFor(() => expect(screen.getByText(/No project selected yet/)).toBeInTheDocument())
  })
})
