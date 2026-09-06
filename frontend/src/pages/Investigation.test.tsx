import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Investigation } from './Investigation'
import { renderWithProviders } from '../test/renderWithProviders'
import { EXPERIMENT_ID } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { apiGet: vi.fn(apiGetMockImpl) }
})

function renderInvestigation(route = `/experiments/${EXPERIMENT_ID}/investigation`) {
  return renderWithProviders(<Investigation />, { route, path: '/experiments/:experimentId/investigation' })
}

describe('Investigation page', () => {
  it('defaults to the abandonment lens and shows the top finding + HOLD recommendation', async () => {
    renderInvestigation()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Abandonment' })).toHaveClass('active'))
    expect(await screen.findByRole('heading', { name: /v2 abandonment is concentrated in/ })).toBeInTheDocument()
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getByText('Decision rule result')).toBeInTheDocument()
  })

  it('switches lenses without merging findings from different lenses', async () => {
    const user = userEvent.setup()
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2 abandonment is concentrated in/ })

    await user.click(screen.getByRole('button', { name: 'Conversion' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Conversion' })).toHaveClass('active'))
    expect(screen.getByRole('button', { name: 'Abandonment' })).not.toHaveClass('active')
  })

  it('selecting a finding updates the mechanism panel', async () => {
    const user = userEvent.setup()
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2 abandonment is concentrated in/ })

    const androidCard = screen.getByText('platform: android').closest('[role="button"]')
    expect(androidCard).toBeTruthy()
    await user.click(androidCard as HTMLElement)

    await waitFor(() => expect(screen.getByRole('heading', { name: /Mechanism: platform: android/ })).toBeInTheDocument())
    expect(screen.getByText(/Non-conversational mechanism: elevated Android latency/)).toBeInTheDocument()
  })

  it('"View sessions" link propagates the finding\'s segment filter as query params', async () => {
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2 abandonment is concentrated in/ })

    const links = screen.getAllByRole('link', { name: /View sessions/i })
    expect(links[0]).toHaveAttribute('href', expect.stringContaining(`experiment_id=${EXPERIMENT_ID}`))
    expect(links[0]).toHaveAttribute('href', expect.stringContaining('constraint_count_bucket=3%2B'))
  })
})
