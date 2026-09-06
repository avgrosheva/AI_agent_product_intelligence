import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RecommendationPanel } from './RecommendationPanel'
import type { Recommendation } from '../../api/types'

const HOLD: Recommendation = {
  verdict: 'hold',
  primary_reason: "Largest excess contribution to the regression is segment 'constraint_count_bucket=3+'.",
  blocking_guardrails: ['p95_latency'],
  next_action: 'Investigate before shipping.',
  rules_applied: ['north star up or flat, but >=1 guardrail breached or a significant negative segment exists -> hold'],
}

describe('RecommendationPanel', () => {
  it('renders the HOLD verdict labeled as a decision rule result, not an LLM opinion', () => {
    render(<RecommendationPanel recommendation={HOLD} />)
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getByText('Decision rule result')).toBeInTheDocument()
    expect(screen.getByText(/Largest excess contribution/)).toBeInTheDocument()
    expect(screen.getByText(/p95_latency/)).toBeInTheDocument()
  })

  it('keeps the rule text collapsed until expanded', async () => {
    const user = userEvent.setup()
    render(<RecommendationPanel recommendation={HOLD} />)
    expect(screen.queryByText(/guardrail breached or a significant negative segment/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Show decision rules/i }))
    expect(screen.getByText(/guardrail breached or a significant negative segment/)).toBeInTheDocument()
  })
})
