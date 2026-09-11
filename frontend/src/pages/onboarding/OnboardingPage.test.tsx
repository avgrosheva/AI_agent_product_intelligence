import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { OnboardingPage } from './OnboardingPage'
import { ActiveProjectProvider } from '../../state/ActiveProjectContext'
import { renderWithProviders } from '../../test/renderWithProviders'
import { resetOnboardingMocks, server, setFailNextConfigSaves } from '../../test/onboardingFixtures'

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client')
  const { createOnboardingApiMocks } = await import('../../test/onboardingFixtures')
  const { apiGet, apiPut, apiPost } = createOnboardingApiMocks(actual.ApiError)
  return { ...actual, apiGet, apiPut, apiPost }
})

function renderOnboarding() {
  return renderWithProviders(
    <ActiveProjectProvider>
      <OnboardingPage />
    </ActiveProjectProvider>,
  )
}

async function goToStep(label: string) {
  fireEvent.click(await screen.findByRole('button', { name: label }))
}

beforeEach(() => {
  resetOnboardingMocks()
})

describe('OnboardingPage', () => {
  it('happy path: shows readiness status and all setup steps for the active project', async () => {
    renderOnboarding()
    await waitFor(() => expect(screen.getByText('Setup readiness')).toBeInTheDocument())
    for (const label of ['Project & domain', 'Data source', 'Metrics', 'Guardrails', 'Segments', 'Economics', 'Monitoring & notifications', 'Review']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('incomplete configuration: surfaces blocking and missing items in plain language', async () => {
    renderOnboarding()
    await waitFor(() => expect(screen.getByText('No primary metric is set -- release decisions cannot be evaluated')).toBeInTheDocument())
    expect(screen.getByText('No sessions have arrived yet')).toBeInTheDocument()
  })

  it('primary metric selection persists through the config API', async () => {
    renderOnboarding()
    await goToStep('Metrics')
    const select = await screen.findByLabelText('Primary metric')
    fireEvent.change(select, { target: { value: 'resolution_rate' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(server.config.primary_metric).toBe('resolution_rate'))
  })

  it('config round trip: a saved value is reflected back after refetch', async () => {
    server.config.primary_metric = 'resolution_rate'
    renderOnboarding()
    await goToStep('Metrics')
    const select = (await screen.findByLabelText('Primary metric')) as HTMLSelectElement
    await waitFor(() => expect(select.value).toBe('resolution_rate'))
  })

  it('guardrail creation appends to the guardrail list without dropping the existing one', async () => {
    renderOnboarding()
    await goToStep('Guardrails')
    await screen.findByText('escalation_rate_guardrail')

    fireEvent.click(screen.getByRole('button', { name: '+ Add a guardrail' }))
    fireEvent.change(screen.getByLabelText('Name (unique)'), { target: { value: 'new_guardrail' } })
    fireEvent.change(screen.getByLabelText('Data column'), { target: { value: 'latency_ms' } })
    fireEvent.change(screen.getByLabelText('Threshold'), { target: { value: '500' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add guardrail' }))

    await waitFor(() => expect(screen.getByText('new_guardrail')).toBeInTheDocument())
    expect(screen.getByText('escalation_rate_guardrail')).toBeInTheDocument()
    const names = (server.config.guardrails as { guardrails: { name: string }[] }).guardrails.map((g) => g.name)
    expect(names).toEqual(['escalation_rate_guardrail', 'new_guardrail'])
  })

  it('validation errors: a rejected save surfaces the backend message clearly', async () => {
    setFailNextConfigSaves(1)
    renderOnboarding()
    await goToStep('Guardrails')
    fireEvent.click(await screen.findByRole('button', { name: '+ Add a guardrail' }))
    fireEvent.change(screen.getByLabelText('Name (unique)'), { target: { value: 'bad_guardrail' } })
    fireEvent.change(screen.getByLabelText('Data column'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Threshold'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add guardrail' }))

    await waitFor(() => expect(screen.getByText(/guardrails: guardrail 'g1' references unknown metric 'totally_unknown'/)).toBeInTheDocument())
  })

  it('segment selection requires at least one allowed value and persists the mapping', async () => {
    renderOnboarding()
    await goToStep('Segments')
    const checkbox = await screen.findByRole('checkbox')
    fireEvent.click(checkbox)
    fireEvent.click(screen.getByRole('button', { name: 'Save segments' }))
    await waitFor(() => expect(screen.getByText(/enter at least one allowed value/)).toBeInTheDocument())

    const input = screen.getByPlaceholderText('allowed values, comma-separated')
    fireEvent.change(input, { target: { value: 'billing, technical' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save segments' }))

    await waitFor(() => expect(server.config.segment_dimensions).toEqual({ ticket_category: ['billing', 'technical'] }))
  })

  it('economics stays optional: submitting blank clears the mapping without error', async () => {
    renderOnboarding()
    await goToStep('Economics')
    fireEvent.click(await screen.findByRole('button', { name: 'Save economics mapping' }))
    await waitFor(() => expect(server.config.economics).toBeNull())
  })

  it('economics: a cost column without a success column is rejected client-side', async () => {
    renderOnboarding()
    await goToStep('Economics')
    fireEvent.change(await screen.findByLabelText('Cost column (optional)'), { target: { value: 'total_cost_usd' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save economics mapping' }))
    await waitFor(() => expect(screen.getByText(/success_column: required/)).toBeInTheDocument())
  })

  it('monitoring/window setup: scheduling a run posts cadence and window_hours', async () => {
    renderOnboarding()
    await goToStep('Monitoring & notifications')
    fireEvent.click(await screen.findByRole('button', { name: '+ Schedule monitoring' }))
    fireEvent.click(screen.getByRole('button', { name: 'Schedule' }))

    await waitFor(() => expect(server.monitoring.configs).toHaveLength(1))
    expect(server.monitoring.configs[0]).toMatchObject({ experiment_id: 'exp-1', cadence_seconds: 3600, window_hours: 24, enabled: true })
  })

  it("project step lets a brand-new team create an organization and first project", async () => {
    server.me = { user: server.me.user, memberships: [], projects: [] }
    renderOnboarding()
    await screen.findByText(/create one to hold your projects/)
    fireEvent.change(screen.getByLabelText('Organization name'), { target: { value: 'New AI Team' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create organization' }))

    await screen.findByLabelText('Project name')
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'First Project' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }))

    await waitFor(() => expect(server.me.projects.some((p) => p.name === 'First Project')).toBe(true))
  })
})

describe('OnboardingPage step gating', () => {
  it('blocks configuration steps until a project is selected', async () => {
    server.me = { user: server.me.user, memberships: server.me.memberships, projects: [] }
    renderOnboarding()
    await goToStep('Metrics')
    expect(await screen.findByText(/Select or create a project/)).toBeInTheDocument()
  })
})
