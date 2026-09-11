import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Investigation } from './Investigation'
import { renderWithProviders } from '../test/renderWithProviders'
import { EXPERIMENT_ID } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { ...actual, apiGet: vi.fn(apiGetMockImpl) }
})

function renderInvestigation(route = `/experiments/${EXPERIMENT_ID}/investigation`) {
  return renderWithProviders(<Investigation />, { route, path: '/experiments/:experimentId/investigation' })
}

describe('Investigation page', () => {
  it("defaults to the project's configured primary metric and shows the top finding + HOLD recommendation", async () => {
    renderInvestigation()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Abandonment rate' })).toHaveClass('active'))
    expect(await screen.findByRole('heading', { name: /v2's change in Abandonment rate is concentrated in/ })).toBeInTheDocument()
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getByText('Decision rule result')).toBeInTheDocument()
  })

  it('switches the primary metric without merging findings from different metrics', async () => {
    const user = userEvent.setup()
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2's change in Abandonment rate is concentrated in/ })

    await user.click(screen.getByRole('button', { name: 'Conversion rate' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Conversion rate' })).toHaveClass('active'))
    expect(screen.getByRole('button', { name: 'Abandonment rate' })).not.toHaveClass('active')
    expect(await screen.findByRole('heading', { name: /v2's change in Conversion rate is concentrated in/ })).toBeInTheDocument()
  })

  it('selecting a finding updates the mechanism panel', async () => {
    const user = userEvent.setup()
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2's change in Abandonment rate is concentrated in/ })

    // Stage 16's segment-effect chart also labels each bar with the
    // segment name, so "platform: android" now appears twice on the page
    // (chart bar + finding card) -- find the one that's actually a
    // clickable finding card.
    const androidCard = screen.getAllByText('platform: android').map((el) => el.closest('[role="button"]')).find((el) => el !== null)
    expect(androidCard).toBeTruthy()
    await user.click(androidCard as HTMLElement)

    await waitFor(() => expect(screen.getByRole('heading', { name: /Mechanism: platform: android/ })).toBeInTheDocument())
    expect(screen.getByText(/Non-conversational mechanism: elevated Android latency/)).toBeInTheDocument()
  })

  it('"View sessions" link propagates the finding\'s segment filter as query params', async () => {
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2's change in Abandonment rate is concentrated in/ })

    const links = screen.getAllByRole('link', { name: /View sessions/i })
    expect(links[0]).toHaveAttribute('href', expect.stringContaining(`experiment_id=${EXPERIMENT_ID}`))
    expect(links[0]).toHaveAttribute('href', expect.stringContaining('constraint_count_bucket=3%2B'))
  })

  it('curates metric tabs to the primary metric and guardrail-watched metrics, not every inferential metric (Stage 17 task 2)', async () => {
    const user = userEvent.setup()
    renderInvestigation()
    await screen.findByRole('heading', { name: /v2's change in Abandonment rate is concentrated in/ })

    // Fixture registers 3 inferential metrics; only 2 are curated
    // (abandonment_rate is primary_metric, conversion_rate is watched by
    // a configured guardrail). clarification_rate is neither.
    expect(screen.getByRole('button', { name: 'Abandonment rate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Conversion rate' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clarification rate' })).not.toBeInTheDocument()

    const showAll = screen.getByRole('button', { name: 'Show all 3 metrics' })
    await user.click(showAll)

    expect(screen.getByRole('button', { name: 'Clarification rate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show fewer' })).toBeInTheDocument()
  })
})
