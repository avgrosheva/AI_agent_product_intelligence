// Presentation-only convention: "is a v2 increase good or bad news for
// this named metric." This is product/domain knowledge (the same
// knowledge a PM has when reading a dashboard), not a statistical
// computation — it never changes a verdict, p-value, or effect size,
// only which color an already-computed delta is drawn in. Metrics not
// listed here render as neutral (no unsupported good/bad claim).

const HIGHER_IS_BETTER = new Set([
  'conversion_rate',
  'add_to_cart_rate',
  'impression_to_click_rate',
  'click_to_cart_rate',
  'cart_to_purchase_rate',
  'tool_success_rate',
  'offline_task_success_rate',
  'constraint_satisfaction_rate',
  'revenue_per_session_usd',
  'gross_margin_proxy_usd',
])

const LOWER_IS_BETTER = new Set([
  'abandonment_rate',
  'time_to_first_recommendation_ms',
  'time_to_goal_seconds',
  'unnecessary_clarification_rate',
  'tool_error_rate',
  'dead_end_rate',
  'cost_per_session_usd',
  'p95_latency',
  'tool_error_rate_guardrail',
])

export type Polarity = 'higher_better' | 'lower_better' | 'neutral'

export function metricPolarity(metricName: string): Polarity {
  if (HIGHER_IS_BETTER.has(metricName)) return 'higher_better'
  if (LOWER_IS_BETTER.has(metricName)) return 'lower_better'
  return 'neutral'
}

/** 'good' | 'bad' | 'neutral' for a v1->v2 delta, given the metric's polarity. */
export function deltaDirection(metricName: string, v1: number | null, v2: number | null): 'good' | 'bad' | 'neutral' {
  if (v1 === null || v2 === null || v1 === v2) return 'neutral'
  const polarity = metricPolarity(metricName)
  if (polarity === 'neutral') return 'neutral'
  const v2Higher = v2 > v1
  if (polarity === 'higher_better') return v2Higher ? 'good' : 'bad'
  return v2Higher ? 'bad' : 'good'
}
