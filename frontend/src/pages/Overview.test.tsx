import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Overview } from './Overview'
import { renderWithProviders } from '../test/renderWithProviders'

vi.mock('../api/client', async () => {
  const { apiGetMockImpl } = await import('../test/fixtures')
  return { apiGet: vi.fn(apiGetMockImpl) }
})

describe('Overview', () => {
  it('renders experiment name, status, north star, and regression signal from the backend', async () => {
    renderWithProviders(<Overview />)

    await waitFor(() => expect(screen.getByText('Conversational Agent v2 Rollout')).toBeInTheDocument())
    expect(screen.getByText('Requires investigation')).toBeInTheDocument()

    await waitFor(() => expect(screen.getByText('Abandonment rate')).toBeInTheDocument())
    expect(screen.getByText('Breach detected')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Investigate/i })).toHaveAttribute('href', expect.stringContaining('/investigation'))
  })

  it('mentions the guardrail breach in the deterministic summary', async () => {
    renderWithProviders(<Overview />)
    await waitFor(() => expect(screen.getByText(/guardrail is breached/i)).toBeInTheDocument())
  })
})
