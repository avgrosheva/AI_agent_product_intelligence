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

export type ClassifierType = 'rule_based_mock' | 'real_llm' | 'unknown' | 'not_classified'
export type EvaluationStatus = 'evaluated_current' | 'evaluated_stale' | 'not_evaluated' | 'not_classified'

export interface ClassifierProvenance {
  classifier_type: ClassifierType
  classifier_version: string | null
  // Populated only when classifier_type === 'real_llm' (e.g. provider
  // "openrouter", model "anthropic/claude-sonnet-5"); null for the mock.
  provider: string | null
  model: string | null
  is_mock: boolean
  evaluation_status: EvaluationStatus
  run_at: string | null
}

export type StatusChip = 'ambiguous_investigate' | 'no_regression_detected' | 'not_yet_investigated'

// ---- Investigation ----
// Finding/Recommendation/ExploredSegmentSummary and their nested types
// below are shared verbatim between the generic investigation response
// (GenericInvestigationResponse, further down) and backend.app.schemas.
// investigation — there is only one Investigation shape now (Stage 16
// retired the legacy commerce-only /investigation endpoint's lens
// concept from the frontend), so there is only one set of types for it.

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

export interface DeterministicDetectorMetric {
  failure_mode: string
  precision: number
  recall: number
  f1: number
  support: number
}

export interface SemanticMechanismMetric {
  failure_mode: string
  precision: number
  recall: number
  f1: number
  support: number
  mean_confidence_correct: number | null
  mean_confidence_incorrect: number | null
}

export interface HybridEvaluationSummary {
  subset: string
  provider: string
  model: string
  prompt_version: string
  detector_version: string
  evaluation_seed: number
  subset_size: number
  deterministic_detectors: DeterministicDetectorMetric[]
  deterministic_detectors_note: string
  semantic_metrics: SemanticMechanismMetric[]
  semantic_micro_precision: number
  semantic_micro_recall: number
  semantic_micro_f1: number
  semantic_macro_f1: number
  semantic_exact_match_ratio: number
  semantic_hamming_loss: number
  semantic_coverage: number
  evaluated_at: string | null
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
  hybrid_evaluation: HybridEvaluationSummary | null
}

export interface ApiErrorBody {
  error_code: string
  detail: string
}

// -- Stage 14: release decision summary ------------------------------

export type ReleaseVerdict = 'SHIP' | 'HOLD' | 'ROLLBACK'
export type DataQualityStatus = 'healthy' | 'warning' | 'critical'
export type Confidence = 'strong' | 'moderate' | 'weak' | 'insufficient_evidence'

export interface DecisionSummary {
  evaluation_id: string
  domain: string
  experiment_id: string
  primary_metric: string
  verdict: ReleaseVerdict
  raw_verdict: ReleaseVerdict
  primary_reason: string
  primary_metric_v1: number | null
  primary_metric_v2: number | null
  primary_metric_delta: number | null
  primary_metric_p_value: number | null
  breached_guardrails: Record<string, unknown>[]
  significant_negative_segment_count: number
  data_quality_status: DataQualityStatus
  data_quality_gated: boolean
  economics_impact: number | null
  confidence: Confidence
}

export interface EvidenceItem {
  rank: number
  category: string
  summary: string
}

export interface FindingExplanation {
  segment_label: string
  dimensions: string[]
  metric: string
  v1_value: number | null
  v2_value: number | null
  delta: number | null
  p_value: number | null
  excess_contribution: number | null
  dominant_failure_mode: string | null
  representative_session_ids: string[]
  next_action: string
}

export interface SessionEvidenceDetail {
  session_id: string
  segment_label: string
  outcome: string
  transcript_excerpt: string[][]
  action_sequence: string[]
  detected_mechanisms: string[]
  human_review_status: 'reviewed' | 'not_reviewed'
  selected_because: string
}

export interface MonitoringWindowInfo {
  data_window_start: string | null
  data_window_end: string | null
  window_hours: number | null
}

export interface ReleaseSummaryResponse {
  decision: DecisionSummary
  explanation_text: string
  evidence_hierarchy: EvidenceItem[]
  findings: FindingExplanation[]
  representative_sessions: SessionEvidenceDetail[]
  economics: Record<string, unknown> | null
  data_quality_status: DataQualityStatus
  monitoring_window: MonitoringWindowInfo
}

// -- Stage 15: auth/org/project + onboarding & project-config UI ----

export interface UserAccount {
  user_id: string
  email: string
  created_at: string
}

export interface Membership {
  membership_id: string
  org_id: string
  user_id: string
  email: string
  role: 'admin' | 'analyst' | 'viewer'
  created_at: string
}

export interface Project {
  project_id: string
  org_id: string
  name: string
  domain: string
  created_at: string
}

export interface Organization {
  org_id: string
  name: string
  created_at: string
}

export interface MeResponse {
  user: UserAccount
  memberships: Membership[]
  projects: Project[]
}

export interface AvailableMetric {
  name: string
  label: string
  metric_type: string
  direction: string
  semantic_class: string
  is_inferential: boolean
  is_descriptive: boolean
  value_column: string | null
}

export interface AvailableGuardrail {
  name: string
  metric: string
  column: string
  aggregation: string
  kind: string
  direction: string
  threshold: number
  severity: string
  enabled: boolean
}

export interface ProjectConfig {
  project_id: string
  primary_metric: string | null
  metrics: { metrics: MetricConfigEntry[] } | null
  guardrails: { guardrails: GuardrailConfigEntry[] } | null
  segment_dimensions: Record<string, string[]> | null
  economics: EconomicsConfigJson | null
  monitoring_cadence_seconds: number | null
  enabled_notification_rules: string[]
  created_at: string | null
  updated_at: string | null
  available_metrics: AvailableMetric[]
  available_guardrails: AvailableGuardrail[]
  available_context_fields: string[]
}

export interface MetricConfigEntry {
  name: string
  label?: string
  type?: string
  direction?: string
  value_column?: string
  is_inferential?: boolean
  is_descriptive?: boolean
  eligibility?: Record<string, unknown>
}

export interface GuardrailConfigEntry {
  name: string
  metric?: string
  column: string
  aggregation: string
  kind?: string
  direction?: string
  threshold: number
  severity?: string
  enabled?: boolean
}

export interface EconomicsConfigJson {
  cost_column?: string
  success_column: string
  value_column?: string
}

export interface ProjectConfigPatch {
  primary_metric?: string | null
  metrics?: { metrics: MetricConfigEntry[] } | null
  guardrails?: { guardrails: GuardrailConfigEntry[] } | null
  segment_dimensions?: Record<string, string[]> | null
  economics?: EconomicsConfigJson | null
  monitoring_cadence_seconds?: number | null
  enabled_notification_rules?: string[] | null
}

export interface OnboardingStatus {
  project_id: string
  domain: string
  ingestion_connected: boolean
  data_received: boolean
  primary_metric_configured: boolean
  guardrails_configured: boolean
  data_quality_status: DataQualityStatus | 'not_applicable'
  monitoring_enabled: boolean
  notifications_configured: boolean
}

export interface DataQualityCheck {
  name: string
  value: number | string | null
  status: string
  detail: string
}

export interface DataQualityReport {
  project_id: string
  domain: string
  status: DataQualityStatus | 'not_applicable'
  generated_at: string
  checks: DataQualityCheck[]
}

export interface MonitoringConfig {
  config_id: string
  project_id: string
  domain: string
  experiment_id: string
  primary_metric: string
  cadence_seconds: number
  window_hours: number | null
  enabled: boolean
  created_at: string
}

export interface MonitoringConfigListResponse {
  configs: MonitoringConfig[]
}

export interface MonitoringRun {
  run_id: string
  config_id: string | null
  project_id: string
  domain: string
  experiment_id: string
  primary_metric: string
  status: 'running' | 'succeeded' | 'failed' | 'skipped_duplicate'
  started_at: string
  completed_at: string | null
  data_window_start: string | null
  data_window_end: string | null
  window_hours: number | null
  release_evaluation_id: string | null
  failure_reason: string | null
}

export interface NotificationChannel {
  channel_id: string
  project_id: string
  channel_type: 'webhook' | 'slack_webhook'
  url_preview: string
  enabled: boolean
  created_at: string
}

export interface NotificationChannelListResponse {
  channels: NotificationChannel[]
}

export interface GenericExperimentSummary {
  experiment_id: string
  name: string
  control_version: string
  treatment_version: string
  start_date: string | null
  end_date: string | null
  n_sessions: number | null
  n_users: number | null
  north_star_metric: MetricResult | null
  status_chip: StatusChip
}

export interface GenericExperimentListResponse {
  domain: string
  experiments: GenericExperimentSummary[]
}

export interface ReleaseEvaluation {
  evaluation_id: string
  domain: string
  experiment_id: string
  primary_metric: string
  status: ReleaseVerdict
  evaluated_at: string
  has_negative_segment: boolean
  any_guardrail_breach: boolean
  primary_reason: string
  next_action: string
  key_metrics: Record<string, unknown>
  breached_guardrails: Record<string, unknown>[]
  top_findings: Record<string, unknown>[]
  project_id: string | null
  economics: Record<string, unknown> | null
  raw_status: ReleaseVerdict
  data_quality_status: DataQualityStatus
  data_quality_gated: boolean
  data_window_start: string | null
  data_window_end: string | null
  window_hours: number | null
}

export interface ReleaseHistoryResponse {
  domain: string
  experiment_id: string
  evaluations: ReleaseEvaluation[]
  total: number
  limit: number
  offset: number
}

// -- Stage 16: the generic, domain-parametrized equivalents of the
// legacy commerce-only endpoints above (backend/app/routers/domains.py)
// -- same field shapes, driven by (domain, project_id) instead of an
// implicit single commerce project, so both commerce and support
// projects render through the same screens.

export interface GenericMetricTableResponse {
  domain: string
  experiment_id: string
  metrics: MetricResult[]
}

export interface GenericGuardrailCheck {
  name: string
  metric: string
  v1_value: number
  v2_value: number
  threshold_description: string
  breached: boolean
  severity: 'blocking' | 'warning'
}

export interface GenericGuardrailResponse {
  domain: string
  experiment_id: string
  checks: GenericGuardrailCheck[]
  any_breach: boolean
  any_warning_breach: boolean
}

export interface GenericInvestigationResponse {
  domain: string
  experiment_id: string
  primary_metric: string
  overall: MetricResult
  guardrails: GenericGuardrailCheck[]
  any_guardrail_breach: boolean
  findings: Finding[]
  explored_not_significant: ExploredSegmentSummary[]
  recommendation: Recommendation
}

export interface Mechanism {
  name: string
  source: 'deterministic' | 'semantic'
  description: string
}

export interface MechanismListResponse {
  domain: string
  mechanisms: Mechanism[]
}

export type ReviewStatus = 'unreviewed' | 'confirmed' | 'rejected' | 'mixed'

export interface GenericSessionSummary {
  session_id: string
  agent_version: string
  outcome: string | null
  started_at: string | null
  detected_mechanisms: string[]
  review_status: ReviewStatus
}

export interface GenericSessionListResponse {
  domain: string
  items: GenericSessionSummary[]
  total: number
  limit: number
  offset: number
}

export interface SegmentDimensionsResponse {
  domain: string
  dimensions: Record<string, string[]>
}

export interface GenericToolCall {
  tool_name: string
  success: boolean
  error_type: string
}

export interface GenericFailureAttribution {
  failure_mode: string
  detector_source: string
  confidence: number | null
  evidence_text: string | null
  review_status: 'unreviewed' | 'confirmed' | 'rejected'
  corrected_mechanism: string | null
  review_note: string | null
}

export interface GenericSessionDetailResponse {
  domain: string
  session_id: string
  outcome: string
  transcript: string[][]
  action_sequence: string[]
  tool_calls: GenericToolCall[]
  failure_attributions: GenericFailureAttribution[]
}

export interface NegativeSegmentEvidence {
  segment_label: string
  dimensions: string[]
  p_value: number | null
  excess_contribution: number | null
  dominant_failure_mode: string | null
  representative_session_ids: string[]
}

export interface SessionEvidence {
  session_id: string
  segment_label: string
  outcome: string
  transcript_excerpt: string[][]
  action_sequence: string[]
}

export interface LinkedMechanism {
  session_id: string
  failure_mode: string
  detector_source: string
  confidence: number | null
  evidence_text: string | null
}

export interface ReleaseEvidenceResponse {
  evaluation_id: string
  domain: string
  experiment_id: string
  status: string
  breached_guardrails: Record<string, unknown>[]
  significant_negative_segments: NegativeSegmentEvidence[]
  representative_sessions: SessionEvidence[]
  linked_failure_mechanisms: LinkedMechanism[]
}

export interface GenericFunnelStagePoint {
  stage: string
  n_sessions: number
  conversion_from_previous: number | null
}

export interface GenericFunnelSeries {
  agent_version: string
  n_sessions: number
  stages: GenericFunnelStagePoint[]
}

export interface GenericFunnelResponse {
  domain: string
  experiment_id: string
  applicable: boolean
  series: GenericFunnelSeries[]
}

export interface GenericFailureMechanismPrevalenceItem {
  failure_mode: string
  detector_source: string
  count_v1: number
  count_v2: number
  rate_v1: number
  rate_v2: number
  reviewed_count: number
  confirmed_count: number
  rejected_count: number
}

export interface GenericToolUseQuality {
  tool_calls_per_session_v1: number | null
  tool_calls_per_session_v2: number | null
  tool_success_rate_v1: number | null
  tool_success_rate_v2: number | null
  tool_error_rate_v1: number | null
  tool_error_rate_v2: number | null
}

export interface GenericTrajectoryPatternItem {
  pattern: string
  n_sessions_v1: number
  n_sessions_v2: number
  negative_outcome_rate_v1: number
  negative_outcome_rate_v2: number
}

export interface GenericAIQualitySummaryResponse {
  domain: string
  experiment_id: string
  failure_mechanism_prevalence: GenericFailureMechanismPrevalenceItem[]
  tool_use_quality: GenericToolUseQuality
  trajectory_patterns: GenericTrajectoryPatternItem[]
}
