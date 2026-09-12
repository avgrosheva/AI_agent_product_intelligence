import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { apiGet } from '../api/client'
import { Overview } from './Overview'
import { renderWithProviders } from '../test/renderWithProviders'
import { apiGetMockImpl, DOMAIN } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { ...actual, apiGet: vi.fn(apiGetMockImpl) }
})

describe('Overview', () => {
  it('renders experiment name, status, and north-star metric from the backend', async () => {
    renderWithProviders(<Overview />)

    await waitFor(() => expect(screen.getByText('Conversational Agent v2 Rollout')).toBeInTheDocument())
    expect(screen.getByText('Requires investigation')).toBeInTheDocument()

    await waitFor(() => expect(screen.getByText('Conversion rate')).toBeInTheDocument())
    expect(screen.getByText('Breach detected')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Investigate/i })).toHaveAttribute('href', expect.stringContaining('/investigation'))
  })

  it('mentions the guardrail breach in the deterministic summary', async () => {
    renderWithProviders(<Overview />)
    await waitFor(() => expect(screen.getByText(/guardrail is breached/i)).toBeInTheDocument())
  })

  it('offers a way to check project setup instead of a dead end when a project has no experiments yet', async () => {
    // Stage 21: a brand-new project with no experiments landed here with
    // only a bare sentence and no link anywhere on the screen -- the
    // actual next step (check what's blocking ingestion/analysis) lives
    // on the Project Overview screen, one click away, but nothing here
    // pointed to it.
    vi.mocked(apiGet).mockImplementation((path, params) => {
      if (path === `/api/v1/domains/${DOMAIN}/experiments`) return Promise.resolve({ domain: DOMAIN, experiments: [] })
      return apiGetMockImpl(path, params)
    })

    renderWithProviders(<Overview />)

    await waitFor(() => expect(screen.getByText('No experiments found for this project yet.')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /check project setup/i })).toHaveAttribute('href', '/project')
  })
})
