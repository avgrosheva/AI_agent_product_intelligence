import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { App } from './App'
import { renderWithProviders } from './test/renderWithProviders'
import { EXPERIMENT_ID } from './test/fixtures'

vi.mock('./api/client', async () => {
  const { apiGetMockImpl } = await import('./test/fixtures')
  return { apiGet: vi.fn(apiGetMockImpl) }
})

describe('App routing', () => {
  it('renders Overview at the root route', async () => {
    renderWithProviders(<App />, { route: '/', path: '*' })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Conversational Agent v2 Rollout' })).toBeInTheDocument())
    expect(await screen.findByRole('link', { name: /Investigate/i })).toBeInTheDocument()
  })

  it('renders the Experiment page at /experiments/:id', async () => {
    renderWithProviders(<App />, { route: `/experiments/${EXPERIMENT_ID}`, path: '*' })
    await waitFor(() => expect(screen.getByText('Experiment metadata')).toBeInTheDocument())
  })

  it('renders the Investigation page at /experiments/:id/investigation', async () => {
    renderWithProviders(<App />, { route: `/experiments/${EXPERIMENT_ID}/investigation`, path: '*' })
    await waitFor(() => expect(screen.getByText(/Ranked findings/)).toBeInTheDocument())
  })

  it('renders the Sessions page', async () => {
    renderWithProviders(<App />, { route: '/sessions', path: '*' })
    await waitFor(() => expect(screen.getByText('Filters')).toBeInTheDocument())
  })

  it('renders the AI Quality page', async () => {
    renderWithProviders(<App />, { route: `/experiments/${EXPERIMENT_ID}/ai-quality`, path: '*' })
    await waitFor(() => expect(screen.getByText('Failure-mode distribution')).toBeInTheDocument())
  })

  it('redirects unknown routes to Overview', async () => {
    renderWithProviders(<App />, { route: '/nonexistent', path: '*' })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Conversational Agent v2 Rollout' })).toBeInTheDocument())
  })
})
