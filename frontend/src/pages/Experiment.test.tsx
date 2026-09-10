import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Experiment } from './Experiment'
import { renderWithProviders } from '../test/renderWithProviders'
import { EXPERIMENT_ID } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { ...actual, apiGet: vi.fn(apiGetMockImpl) }
})

describe('Experiment page', () => {
  it('renders metadata, the full metric table, funnel, and guardrails', async () => {
    renderWithProviders(<Experiment />, { route: `/experiments/${EXPERIMENT_ID}`, path: '/experiments/:experimentId' })
    await waitFor(() => expect(screen.getByText('Experiment metadata')).toBeInTheDocument())
    expect(screen.getByText('Conversion rate')).toBeInTheDocument()
    expect(screen.getByText('Abandonment rate')).toBeInTheDocument()
    expect(screen.getByText('Shopping funnel')).toBeInTheDocument()
    expect(screen.getByText('p95 latency')).toBeInTheDocument()
  })

  it('filters the metric table by semantic-class group', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Experiment />, { route: `/experiments/${EXPERIMENT_ID}`, path: '/experiments/:experimentId' })
    await waitFor(() => expect(screen.getByText('Conversion rate')).toBeInTheDocument())
    expect(screen.getByText('Cost per session (USD)')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Product outcome' }))

    expect(screen.getByText('Conversion rate')).toBeInTheDocument()
    expect(screen.queryByText('Cost per session (USD)')).not.toBeInTheDocument()
    expect(screen.queryByText('Clarification rate')).not.toBeInTheDocument()
  })
})
