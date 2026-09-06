// Mirrors backend/investigation/segments.py's DIMENSION_VALUES,
// backend/llm/client.py's FAILURE_TAXONOMY, and datagen's outcome values —
// used only to populate filter dropdowns on the Sessions screen. This is
// not a computation and never drives any statistic; if the backend
// registry changes, these lists must be updated to match, but no analysis
// depends on them being correct (the API validates/filters server-side).

export const DIMENSION_VALUES: Record<string, string[]> = {
  agent_version: ['v1', 'v2'],
  requested_category: ['laptop', 'monitor', 'accessory'],
  constraint_count_bucket: ['0-1', '2', '3+'],
  platform: ['web', 'ios', 'android'],
  device_tier: ['low', 'mid', 'high'],
  locale: ['ru-RU', 'en-US'],
  persona: ['budget', 'mainstream', 'power_user', 'gift_buyer'],
  outcome: ['abandoned', 'no_action', 'add_to_cart_only', 'purchase'],
  failure_mode: [
    'unnecessary_clarification',
    'wrong_constraint_interpretation',
    'poor_ranking',
    'wrong_tool_selection',
    'unsupported_product_claim',
    'retrieval_failure',
    'other',
    'none',
  ],
}

export const FILTERABLE_DIMENSIONS: { key: string; label: string }[] = [
  { key: 'agent_version', label: 'Version' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'failure_mode', label: 'Failure mode' },
  { key: 'platform', label: 'Platform' },
  { key: 'requested_category', label: 'Category' },
  { key: 'constraint_count_bucket', label: 'Constraints' },
  { key: 'device_tier', label: 'Device tier' },
  { key: 'locale', label: 'Locale' },
  { key: 'persona', label: 'Persona' },
]
