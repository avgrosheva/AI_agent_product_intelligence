// Mirrors backend/app/schemas/*.py field-for-field. Do not add derived
// fields here — this file is a typed reflection of the API contract, not a
// place to invent data. Any computed/derived display value belongs in a
// component, built from these fields, never a new statistic.

export type SemanticClass = 'pre_treatment' | 'treatment' | 'post_treatment_mechanism' | 'outcome' | 'economic_outcome'
export type Verdict = 'significant' | 'not_significant' | 'insufficient_evidence'

export interface MetricResult {
  metric_name: string
  segment: string
  semantic_class: SemanticClass
  is_descriptive: boolean
  is_inferential: boolean
  n_sessions_v1: number
  n_sessions_v2: number
  session_value_v1: number
  session_value_v2: number
  n_users_v1: number
  n_users_v2: number
  cluster_mean_v1: number | null
  cluster_mean_v2: number | null
  event_count_v1: number | null
  event_count_v2: number | null
  non_event_count_v1: number | null
  non_event_count_v2: number | null
  test_name: string | null
  p_value: number | null
  effect_size_name: string | null
  effect_size_value: number | null
  ci_low: number | null
  ci_high: number | null
  ci_stat: string | null
  verdict: Verdict
  notes: string[]
}

export type ClassifierType = 'rule_based_mock' | 'anthropic' | 'unknown' | 'not_classified'
export type EvaluationStatus = 'evaluated_current' | 'evaluated_stale' | 'not_evaluated' | 'not_classified'

export interface ClassifierProvenance {
  classifier_type: ClassifierType
  classifier_version: string | null
  is_mock: boolean
  evaluation_status: EvaluationStatus
  run_at: string | null
}

export type StatusChip = 'ambiguous_investigate' | 'no_regression_detected' | 'not_yet_investigated'

export interface ExperimentSummary {
  experiment_id: string
  name: string
  control_version: string
  treatment_version: string
  start_date: string
  end_date: string
  status: string
  n_sessions: number
  n_users: number
  north_star_metric: MetricResult
  status_chip: StatusChip
}

export interface ExperimentListResponse {
  experiments: ExperimentSummary[]
}

export interface ExperimentDetail {
  experiment_id: string
  name: string
  control_version: string
  treatment_version: string
  start_date: string
  end_date: string
  status: string
  traffic_split: number
  n_sessions_v1: number
  n_sessions_v2: number
  n_users_v1: number
  n_users_v2: number
}

export interface MetricTableResponse {
  experiment_id: string
  metrics: MetricResult[]
}

export interface FunnelStep {
  agent_version: 'v1' | 'v2'
  n_sessions: number
  n_impression: number
  n_click: number
  n_cart: number
  n_purchase: number
  impression_to_click_rate: number | null
  click_to_cart_rate: number | null
  cart_to_purchase_rate: number | null
}

export interface FunnelResponse {
  experiment_id: string
  funnel: FunnelStep[]
}

export interface GuardrailCheck {
  name: string
  v1_value: number
  v2_value: number
  threshold_description: string
  breached: boolean
}

export interface GuardrailResponse {
  experiment_id: string
  checks: GuardrailCheck[]
  any_breach: boolean
}

// ---- Investigation ----

export type InvestigationLens = 'abandonment' | 'conversion' | 'constraint_satisfaction'
export type LensRole = 'primary_regression_lens' | 'north_star_context' | 'ai_quality_lens'

export interface SegmentFilter {
  dimensions: Record<string, string>
}

export interface FailureModeShare {
  failure_mode: string
  excess_count: number
  share_of_excess_abandonment: number | null
  raw_share_of_v2_failures: number | null
}

export interface FailureAttribution {
  n_v1: number
  n_v2: number
  abandonment_rate_v1: number
  abandonment_rate_v2: number
  total_excess_abandonment: number
  reportable: boolean
  per_mode: FailureModeShare[]
}

export interface TrajectoryAssociation {
  pattern: string
  n_sessions: number
  pattern_outcome_rate: number
  baseline_outcome_rate: number
  test_name: string
  p_value: number
  bh_significant: boolean
}

export interface Finding {
  segment_label: string
  segment_filter: SegmentFilter
  n_users_v1: number
  n_users_v2: number
  cluster_mean_v1: number
  cluster_mean_v2: number
  p_value: number
  effect_size_value: number | null
  excess_contribution: number
  dominant_failure_mode: string | null
  failure_attribution: FailureAttribution
  trajectory_associations: TrajectoryAssociation[]
}

export type RecommendationVerdict = 'ship' | 'hold' | 'roll_back'

export interface Recommendation {
  verdict: RecommendationVerdict
  primary_reason: string
  blocking_guardrails: string[]
  next_action: string
  rules_applied: string[]
}

export interface ExploredSegmentSummary {
  segment_label: string
  p_value: number | null
  bh_significant: boolean
  meets_min_effect: boolean
  verdict: string
}

export interface InvestigationResponse {
  experiment_id: string
  lens: InvestigationLens
  lens_role: LensRole
  lens_description: string
  primary_metric: string
  overall: MetricResult
  guardrails: GuardrailCheck[]
  any_guardrail_breach: boolean
  findings: Finding[]
  explored_not_significant: ExploredSegmentSummary[]
  recommendation: Recommendation
}

// ---- Sessions ----

export interface SessionSummary {
  session_id: string
  agent_version: string
  requested_category: string
  constraint_count_bucket: string
  platform: string
  device_tier: string
  locale: string
  persona: string
  outcome: string
  num_turns: number
  total_latency_ms: number
  total_cost_usd: number
  started_at: string
  failure_mode: string | null
}

export interface SessionListResponse {
  items: SessionSummary[]
  total: number
  limit: number
  offset: number
  filters_applied: Record<string, string>
}

export interface MessageItem {
  turn_index: number
  sender: string
  text: string
  tokens: number
  latency_ms: number | null
  created_at: string
}

export interface AgentAction {
  sequence_index: number
  action_type: string
  latency_ms: number
  model_name: string
  started_at: string
}

export interface ToolCall {
  tool_name: string
  success: boolean
  error_type: string
  latency_ms: number
  action_sequence_index: number
  action_started_at: string
}

export interface RecommendationItem {
  product_id: string
  rank_position: number
  clicked: boolean
  satisfies_constraints: boolean
}

export interface ProductEvent {
  event_type: string
  event_time: string
  price_at_event: number
}

export interface EvaluationItem {
  eval_type: string
  score: number
  evaluator: string
}

export interface FailureClassification {
  failure_mode: string
  confidence: number
  evidence_text: string
  source: string
  provenance: ClassifierProvenance
}

export interface SessionDetail {
  session_id: string
  agent_version: string
  requested_category: string
  constraint_count_bucket: string
  platform: string
  device_tier: string
  locale: string
  persona: string
  num_constraints: number
  outcome: string
  num_turns: number
  total_latency_ms: number
  total_tokens_in: number
  total_tokens_out: number
  total_cost_usd: number
  started_at: string
  ended_at: string | null
  transcript: MessageItem[]
  agent_actions: AgentAction[]
  tool_calls: ToolCall[]
  recommendations: RecommendationItem[]
  product_events: ProductEvent[]
  evaluations: EvaluationItem[]
  failure_classification: FailureClassification | null
}

// ---- AI Quality ----

export interface FailureModeDistributionItem {
  failure_mode: string
  count_v1: number
  count_v2: number
  rate_v1: number
  rate_v2: number
}

export interface ToolUseQuality {
  tool_calls_per_session_v1: number
  tool_calls_per_session_v2: number
  tool_success_rate_v1: number
  tool_success_rate_v2: number
  tool_error_rate_v1: number
  tool_error_rate_v2: number
}

export interface TrajectoryPatternFrequency {
  pattern: string
  n_sessions_v1: number
  n_sessions_v2: number
  abandonment_rate_v1: number
  abandonment_rate_v2: number
}

export interface ClassifierPerClassMetric {
  failure_mode: string
  support: number
  precision: number | null
  recall: number | null
  f1: number | null
}

export interface ClassifierAcceptanceBar {
  failure_mode: string
  recall: number
  recall_bar: number
  recall_pass: boolean
  precision: number
  precision_bar: number
  precision_pass: boolean
}

export interface ClassifierEvaluationResponse {
  provenance: ClassifierProvenance
  n_sessions_evaluated: number | null
  overall_accuracy: number | null
  mean_confidence_correct: number | null
  mean_confidence_incorrect: number | null
  per_class_metrics: ClassifierPerClassMetric[]
  acceptance_bars: ClassifierAcceptanceBar[]
  all_acceptance_bars_met: boolean | null
}

export interface AIQualitySummaryResponse {
  experiment_id: string
  failure_mode_distribution: FailureModeDistributionItem[]
  tool_use_quality: ToolUseQuality
  trajectory_patterns: TrajectoryPatternFrequency[]
  classifier_provenance: ClassifierProvenance
}

export interface ApiErrorBody {
  error_code: string
  detail: string
}
