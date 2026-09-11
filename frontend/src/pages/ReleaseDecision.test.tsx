import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { ApiError, apiGet } from '../api/client'
import { ReleaseDecision } from './ReleaseDecision'
import { renderWithProviders } from '../test/renderWithProviders'
import { apiGetMockImpl, DOMAIN, EXPERIMENT_ID } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { ...actual, apiGet: vi.fn(apiGetMockImpl) }
})

describe('ReleaseDecision', () => {
  it('shows the verdict prominently and the deterministic explanation', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('ROLLBACK')).toBeInTheDocument())
    expect(screen.getByText(/ROLLBACK because abandonment_rate increased by 15\.0pp/)).toBeInTheDocument()
  })

  it('shows the primary metric change, guardrail breach, and economics impact', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('Breach detected')).toBeInTheDocument())
    expect(screen.getByText('p95 latency')).toBeInTheDocument()
    expect(screen.getByText('Negative impact')).toBeInTheDocument()
  })

  it('shows the evidence hierarchy in rank order', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('Why this decision?')).toBeInTheDocument())
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Blocking guardrail')
    expect(items[1]).toHaveTextContent('Primary metric')
    expect(items[2]).toHaveTextContent('negative excess contribution')
  })

  it('shows significant findings with next action', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('Significant findings')).toBeInTheDocument())
    expect(screen.getByText(/Review retrieval quality for electronics-category queries/)).toBeInTheDocument()
  })

  it('shows representative sessions with review status and selection reason', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('Representative sessions')).toBeInTheDocument())
    expect(screen.getByText('not reviewed')).toBeInTheDocument()
    expect(screen.getByText(/Sampled from the treatment arm/)).toBeInTheDocument()
  })

  it('shows data quality and monitoring window', async () => {
    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText('Data quality')).toBeInTheDocument())
    expect(screen.getByText('healthy')).toBeInTheDocument()
    expect(screen.getByText('Manual evaluation — full history, no time window.')).toBeInTheDocument()
  })

  it('shows the empty state with an Evaluate now button, not a raw error, when this experiment has no evaluation yet (Stage 17 task 10)', async () => {
    // Stage 17: a Playwright E2E run against the real backend caught
    // this -- release-summary 404s for an experiment that's never been
    // evaluated (an entirely expected state, not a request failure), but
    // the page's single `if (error) return <ErrorState />` branch caught
    // that 404 before ever reaching the intended "no evaluation yet"
    // empty state, so the ONLY way out of the screen (the Evaluate now
    // button) never rendered.
    vi.mocked(apiGet).mockImplementation((path, params) => {
      if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/release-summary`) {
        return Promise.reject(new ApiError(404, `No release evaluation has been run yet for domain='${DOMAIN}' experiment_id='${EXPERIMENT_ID}'`))
      }
      return apiGetMockImpl(path, params)
    })

    renderWithProviders(<ReleaseDecision />, { route: `/experiments/${EXPERIMENT_ID}/release`, path: '/experiments/:experimentId/release' })
    await waitFor(() => expect(screen.getByText(/No release evaluation has been run yet/)).toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Evaluate now' })).toBeInTheDocument())
    expect(screen.queryByText(/Not found/)).not.toBeInTheDocument()
  })
})
