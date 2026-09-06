import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState, ErrorState, LoadingState } from './States'

describe('shared state components', () => {
  it('LoadingState announces itself for screen readers', () => {
    render(<LoadingState label="Loading experiments…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading experiments…')
  })

  it('ErrorState renders as an alert with the error message', () => {
    render(<ErrorState message="Network unreachable" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Network unreachable')
  })

  it('EmptyState renders custom empty-state content', () => {
    render(<EmptyState>No sessions match these filters.</EmptyState>)
    expect(screen.getByText('No sessions match these filters.')).toBeInTheDocument()
  })
})
