import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState, ErrorState, LoadingState } from './States'
import { ApiError } from '../../api/client'

describe('shared state components', () => {
  it('LoadingState announces itself for screen readers', () => {
    render(<LoadingState label="Loading experiments…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading experiments…')
  })

  it('ErrorState renders a plain string error as a generic alert', () => {
    render(<ErrorState error="Network unreachable" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Network unreachable')
  })

  it('ErrorState distinguishes access-denied (401/403) from a generic failure (Stage 17 task 4)', () => {
    render(<ErrorState error={new ApiError(403, 'You are not a member of this project')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Access denied')
    expect(screen.getByRole('alert')).toHaveTextContent('You are not a member of this project')
  })

  it('ErrorState distinguishes not-found (404) from a generic failure', () => {
    render(<ErrorState error={new ApiError(404, 'No release evaluation has been run yet')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Not found')
  })

  it('ErrorState shows the backend detail text, not a raw error, for a 500', () => {
    render(<ErrorState error={new ApiError(500, 'Internal Server Error')} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Request failed')
    expect(screen.getByRole('alert')).toHaveTextContent('Internal Server Error')
  })

  it('EmptyState renders custom empty-state content', () => {
    render(<EmptyState>No sessions match these filters.</EmptyState>)
    expect(screen.getByText('No sessions match these filters.')).toBeInTheDocument()
  })
})
