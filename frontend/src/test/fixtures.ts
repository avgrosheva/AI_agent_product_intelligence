import type {
  AvailableMetric,
  ClassifierEvaluationResponse,
  GenericAIQualitySummaryResponse,
  GenericExperimentListResponse,
  GenericFunnelResponse,
  GenericGuardrailResponse,
  GenericInvestigationResponse,
  GenericMetricTableResponse,
  GenericSessionDetailResponse,
  GenericSessionListResponse,
  MeResponse,
  MetricResult,
  ProjectConfig,
  ReleaseSummaryResponse,
} from '../api/types'

export const EXPERIMENT_ID = 'exp-1234'
export const PROJECT_ID = 'proj-commerce-0001'
export const ORG_ID = 'org-commerce-0001'
export const DOMAIN = 'commerce'

function metric(overrides: Partial<MetricResult> = {}): MetricResult {
  return {
    metric_name: 'conversion_rate',
    segment: 'all sessions',
    semantic_class: 'outcome',
    is_descriptive: true,
    is_inferential: true,
    n_sessions_v1: 1000,
    n_sessions_v2: 1000,
    session_value_v1: 0.2,
    session_value_v2: 0.19,
    n_users_v1: 300,
    n_users_v2: 300,
    cluster_mean_v1: 0.2,
    cluster_mean_v2: 0.19,
    event_count_v1: 200,
    event_count_v2: 190,
    non_event_count_v1: null,
    non_event_count_v2: null,
    test_name: 'welch_t',
    p_value: 0.36,
    effect_size_name: 'cohens_d_avg_variance',
    effect_size_value: -0.03,
    ci_low: -0.02,
    ci_high: 0.01,
    ci_stat: 'mean_diff',
    verdict: 'not_significant',
    notes: [],
    ...overrides,
  }
}

/** Stage 16: every screen is now project/domain-scoped, so a single
 * one-project account is the default test fixture — the same shape a
 * real single-project login has, matching what these tests asserted
 * before Stage 15/16 introduced multi-project accounts at all. */
export const ME_FIXTURE: MeResponse = {
  user: { user_id: 'user-1', email: 'demo@example.com', created_at: '2026-01-01T00:00:00Z' },
  memberships: [{ membership_id: 'mem-1', org_id: ORG_ID, user_id: 'user-1', email: 'demo@example.com', role: 'admin', created_at: '2026-01-01T00:00:00Z' }],
  projects: [{ project_id: PROJECT_ID, org_id: ORG_ID, name: 'Commerce Test Project', domain: DOMAIN, created_at: '2026-01-01T00:00:00Z' }],
}

const NORTH_STAR_METRIC = metric()

export const GENERIC_EXPERIMENTS_FIXTURE: GenericExperimentListResponse = {
  domain: DOMAIN,
  experiments: [
    {
      experiment_id: EXPERIMENT_ID,
      name: 'Conversational Agent v2 Rollout',
      control_version: 'v1',
      treatment_version: 'v2',
      start_date: '2024-01-01',
      end_date: '2024-02-01',
      n_sessions: 32299,
      n_users: 9000,
      north_star_metric: NORTH_STAR_METRIC,
      status_chip: 'ambiguous_investigate',
    },
  ],
}

export const GENERIC_METRICS_FIXTURE: GenericMetricTableResponse = {
  domain: DOMAIN,
  experiment_id: EXPERIMENT_ID,
  metrics: [
    metric({ metric_name: 'conversion_rate', semantic_class: 'outcome' }),
    metric({
      metric_name: 'abandonment_rate', semantic_class: 'outcome',
      cluster_mean_v1: 0.169, cluster_mean_v2: 0.219, p_value: 8.5e-23, verdict: 'significant', effect_size_value: 0.21,
    }),
    metric({
      metric_name: 'clarification_rate', semantic_class: 'post_treatment_mechanism',
      cluster_mean_v1: 0.26, cluster_mean_v2: 0.38, p_value: 1e-99, verdict: 'significant',
    }),
    metric({
      metric_name: 'cost_per_session_usd', semantic_class: 'economic_outcome',
      cluster_mean_v1: 0.0052, cluster_mean_v2: 0.0053, p_value: 0.01, verdict: 'significant',
    }),
  ],
}

export const GENERIC_FUNNEL_FIXTURE: GenericFunnelResponse = {
  domain: DOMAIN,
  experiment_id: EXPERIMENT_ID,
  applicable: true,
  series: [
    {
      agent_version: 'v1', n_sessions: 16188,
      stages: [
        { stage: 'impression', n_sessions: 12000, conversion_from_previous: null },
        { stage: 'click', n_sessions: 6300, conversion_from_previous: 0.525 },
        { stage: 'cart', n_sessions: 4586, conversion_from_previous: 0.728 },
        { stage: 'purchase', n_sessions: 3181, conversion_from_previous: 0.694 },
      ],
    },
    {
      agent_version: 'v2', n_sessions: 16111,
      stages: [
        { stage: 'impression', n_sessions: 11500, conversion_from_previous: null },
        { stage: 'click', n_sessions: 6000, conversion_from_previous: 0.521 },
        { stage: 'cart', n_sessions: 4287, conversion_from_previous: 0.715 },
        { stage: 'purchase', n_sessions: 2986, conversion_from_previous: 0.697 },
      ],
    },
  ],
}

export const GENERIC_GUARDRAILS_FIXTURE: GenericGuardrailResponse = {
  domain: DOMAIN,
  experiment_id: EXPERIMENT_ID,
  any_breach: true,
  any_warning_breach: false,
  checks: [
    { name: 'p95_latency', metric: 'p95_latency_ms', v1_value: 2187.65, v2_value: 2954.0, threshold_description: 'v2 p95 latency must not exceed v1 by more than 15%', breached: true, severity: 'blocking' },
    { name: 'tool_error_rate', metric: 'tool_error_rate', v1_value: 0.068, v2_value: 0.064, threshold_description: 'v2 tool error rate must not exceed v1 by more than 2pp', breached: false, severity: 'blocking' },
    { name: 'cost_per_session', metric: 'cost_per_session_usd', v1_value: 0.0052, v2_value: 0.0053, threshold_description: 'v2 cost must not exceed v1 by more than 20%', breached: false, severity: 'warning' },
  ],
}

const INFERENTIAL_METRICS: AvailableMetric[] = [
  { name: 'abandonment_rate', label: 'Abandonment rate', metric_type: 'rate', direction: 'lower_is_better', semantic_class: 'outcome', is_inferential: true, is_descriptive: true, value_column: 'abandoned' },
  { name: 'conversion_rate', label: 'Conversion rate', metric_type: 'rate', direction: 'higher_is_better', semantic_class: 'outcome', is_inferential: true, is_descriptive: true, value_column: 'converted' },
  // Not the primary metric, not watched by any configured guardrail --
  // stays out of the curated default tab set (Stage 17 task 2) until
  // "Show all metrics" is clicked.
  { name: 'clarification_rate', label: '', metric_type: 'rate', direction: 'higher_is_better', semantic_class: 'post_treatment_mechanism', is_inferential: true, is_descriptive: true, value_column: 'has_clarify' },
]

export const PROJECT_CONFIG_FIXTURE: ProjectConfig = {
  project_id: PROJECT_ID,
  primary_metric: 'abandonment_rate',
  metrics: null,
  guardrails: null,
  segment_dimensions: null,
  economics: null,
  monitoring_cadence_seconds: null,
  enabled_notification_rules: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  available_metrics: INFERENTIAL_METRICS,
  // A guardrail watching conversion_rate keeps it in Investigation's
  // curated metric-tab set (Stage 17 task 2) alongside the primary
  // metric abandonment_rate, without relying on a custom metrics config.
  available_guardrails: [
    { name: 'conversion_guardrail', metric: 'conversion_rate', column: 'converted', aggregation: 'cluster_mean', kind: 'absolute', direction: 'decrease_is_bad', threshold: 0.05, severity: 'warning', enabled: true },
  ],
  available_context_fields: [],
}

export function genericInvestigationFixture(primaryMetric = 'abandonment_rate'): GenericInvestigationResponse {
  return {
    domain: DOMAIN,
    experiment_id: EXPERIMENT_ID,
    primary_metric: primaryMetric,
    overall: metric({ metric_name: primaryMetric, cluster_mean_v1: 0.169, cluster_mean_v2: 0.219, p_value: 8.5e-23, verdict: 'significant' }),
    guardrails: GENERIC_GUARDRAILS_FIXTURE.checks,
    any_guardrail_breach: true,
    findings: [
      {
        segment_label: 'constraint_count_bucket=3+',
        segment_filter: { dimensions: { constraint_count_bucket: '3+' } },
        n_users_v1: 229, n_users_v2: 208,
        cluster_mean_v1: 0.176, cluster_mean_v2: 0.323,
        p_value: 1.5e-58, effect_size_value: 0.4, excess_contribution: 0.071,
        dominant_failure_mode: 'unnecessary_clarification',
        failure_attribution: {
          n_v1: 229, n_v2: 208, abandonment_rate_v1: 0.176, abandonment_rate_v2: 0.323, total_excess_abandonment: 30.5, reportable: true,
          per_mode: [
            { failure_mode: 'unnecessary_clarification', excess_count: 28.0, share_of_excess_abandonment: 0.92, raw_share_of_v2_failures: 0.6 },
            { failure_mode: 'none', excess_count: 2.5, share_of_excess_abandonment: 0.08, raw_share_of_v2_failures: 0.1 },
          ],
        },
        trajectory_associations: [
          { pattern: 'exact:understand_query>search>clarify>search>recommend', n_sessions: 200, pattern_outcome_rate: 0.6, baseline_outcome_rate: 0.68, test_name: 'chi_square', p_value: 0.001, bh_significant: true },
        ],
      },
      {
        segment_label: 'platform=android',
        segment_filter: { dimensions: { platform: 'android' } },
        n_users_v1: 300, n_users_v2: 290,
        cluster_mean_v1: 0.18, cluster_mean_v2: 0.328,
        p_value: 6.1e-40, effect_size_value: 0.43, excess_contribution: 0.042,
        dominant_failure_mode: 'unnecessary_clarification',
        failure_attribution: {
          n_v1: 300, n_v2: 290, abandonment_rate_v1: 0.18, abandonment_rate_v2: 0.328, total_excess_abandonment: 43.0, reportable: true,
          per_mode: [{ failure_mode: 'unnecessary_clarification', excess_count: 20.0, share_of_excess_abandonment: 0.46, raw_share_of_v2_failures: 0.3 }],
        },
        trajectory_associations: [],
      },
    ],
    explored_not_significant: [
      { segment_label: 'device_tier=low', p_value: 0.4, bh_significant: false, meets_min_effect: false, verdict: 'not_significant' },
    ],
    recommendation: {
      verdict: 'hold',
      primary_reason: "Largest excess contribution to the regression is segment 'constraint_count_bucket=3+'.",
      blocking_guardrails: ['p95_latency'],
      next_action: 'Investigate constraint-heavy clarification behavior before shipping.',
      rules_applied: ['north star up or flat, but >=1 guardrail breached or a significant negative segment exists -> hold'],
    },
  }
}

export const GENERIC_AI_QUALITY_FIXTURE: GenericAIQualitySummaryResponse = {
  domain: DOMAIN,
  experiment_id: EXPERIMENT_ID,
  failure_mechanism_prevalence: [
    { failure_mode: 'unnecessary_clarification', detector_source: 'mock_llm', count_v1: 100, count_v2: 400, rate_v1: 0.02, rate_v2: 0.09, reviewed_count: 0, confirmed_count: 0, rejected_count: 0 },
    { failure_mode: 'retrieval_failure', detector_source: 'deterministic', count_v1: 300, count_v2: 250, rate_v1: 0.06, rate_v2: 0.05, reviewed_count: 0, confirmed_count: 0, rejected_count: 0 },
  ],
  tool_use_quality: {
    tool_calls_per_session_v1: 1.89, tool_calls_per_session_v2: 1.85,
    tool_success_rate_v1: 0.93, tool_success_rate_v2: 0.94,
    tool_error_rate_v1: 0.068, tool_error_rate_v2: 0.064,
  },
  trajectory_patterns: [
    { pattern: 'exact:understand_query>search>recommend', n_sessions_v1: 4000, n_sessions_v2: 3900, negative_outcome_rate_v1: 0.15, negative_outcome_rate_v2: 0.16 },
  ],
  human_review_quality: {
    overall: { reviewed_count: 12, confirmed_count: 9, rejected_count: 3, corrected_count: 2, confirmation_rate: 0.75, correction_rate: 1 / 6, sample_status: 'enough_data' },
    by_mechanism: [
      {
        failure_mode: 'unnecessary_clarification', detector_source: 'mock_llm',
        counts: { reviewed_count: 10, confirmed_count: 8, rejected_count: 2, corrected_count: 1, confirmation_rate: 0.8, correction_rate: 0.1, sample_status: 'enough_data' },
      },
      {
        failure_mode: 'retrieval_failure', detector_source: 'deterministic',
        counts: { reviewed_count: 2, confirmed_count: 1, rejected_count: 1, corrected_count: 1, confirmation_rate: 0.5, correction_rate: 0.5, sample_status: 'insufficient_review_data' },
      },
    ],
    by_detector_source: [
      { detector_source: 'mock_llm', counts: { reviewed_count: 10, confirmed_count: 8, rejected_count: 2, corrected_count: 1, confirmation_rate: 0.8, correction_rate: 0.1, sample_status: 'enough_data' } },
      { detector_source: 'deterministic', counts: { reviewed_count: 2, confirmed_count: 1, rejected_count: 1, corrected_count: 1, confirmation_rate: 0.5, correction_rate: 0.5, sample_status: 'insufficient_review_data' } },
    ],
    by_confidence_bucket: [
      { bucket_label: '0.0-0.5', bucket_min: 0.0, bucket_max: 0.5, counts: { reviewed_count: 0, confirmed_count: 0, rejected_count: 0, corrected_count: 0, confirmation_rate: null, correction_rate: null, sample_status: 'insufficient_review_data' } },
      { bucket_label: '0.5-0.7', bucket_min: 0.5, bucket_max: 0.7, counts: { reviewed_count: 2, confirmed_count: 1, rejected_count: 1, corrected_count: 0, confirmation_rate: 0.5, correction_rate: 0.0, sample_status: 'insufficient_review_data' } },
      { bucket_label: '0.7-0.9', bucket_min: 0.7, bucket_max: 0.9, counts: { reviewed_count: 4, confirmed_count: 3, rejected_count: 1, corrected_count: 1, confirmation_rate: 0.75, correction_rate: 0.25, sample_status: 'insufficient_review_data' } },
      { bucket_label: '0.9-1.0', bucket_min: 0.9, bucket_max: 1.0, counts: { reviewed_count: 6, confirmed_count: 5, rejected_count: 1, corrected_count: 1, confirmation_rate: 0.833, correction_rate: 0.167, sample_status: 'insufficient_review_data' } },
    ],
    by_version: [
      {
        detector_version: 'rule_based_mock-v1', provider: null, model: null, prompt_version: null,
        first_seen: '2026-01-01T00:00:00Z', last_seen: '2026-01-10T00:00:00Z',
        counts: { reviewed_count: 10, confirmed_count: 8, rejected_count: 2, corrected_count: 1, confirmation_rate: 0.8, correction_rate: 0.1, sample_status: 'enough_data' },
      },
      {
        detector_version: 'rule_based_mock-v2', provider: null, model: null, prompt_version: null,
        first_seen: '2026-02-01T00:00:00Z', last_seen: '2026-02-02T00:00:00Z',
        counts: { reviewed_count: 2, confirmed_count: 1, rejected_count: 1, corrected_count: 1, confirmation_rate: 0.5, correction_rate: 0.5, sample_status: 'insufficient_review_data' },
      },
    ],
    disagreement_items: [
      {
        session_id: 'sess-0001-aaaa-bbbb-cccc-000000000001', experiment_id: EXPERIMENT_ID, original_mechanism: 'unnecessary_clarification',
        corrected_mechanism: 'wrong_tool_selection', original_confidence: 0.6, detector_source: 'mock_llm',
        detector_version: 'rule_based_mock-v1', provider: null, model: null, prompt_version: null,
        reviewed_at: '2026-01-05T00:00:00Z',
      },
    ],
    confusion_pairs: [
      { original_mechanism: 'unnecessary_clarification', corrected_mechanism: 'wrong_tool_selection', count: 2 },
    ],
    min_reviews_threshold: 10,
  },
}

export const CLASSIFIER_EVALUATION_FIXTURE: ClassifierEvaluationResponse = {
  provenance: {
    classifier_type: 'rule_based_mock',
    classifier_version: 'rule_based_mock-v1',
    provider: null,
    model: null,
    is_mock: true,
    evaluation_status: 'evaluated_current',
    run_at: '2024-02-01T00:00:00Z',
  },
  n_sessions_evaluated: 32299,
  overall_accuracy: 0.871,
  mean_confidence_correct: 0.88,
  mean_confidence_incorrect: 0.73,
  per_class_metrics: [
    { failure_mode: 'unnecessary_clarification', support: 3783, precision: 1.0, recall: 1.0, f1: 1.0 },
  ],
  acceptance_bars: [
    { failure_mode: 'unnecessary_clarification', recall: 1.0, recall_bar: 0.7, recall_pass: true, precision: 1.0, precision_bar: 0.6, precision_pass: true },
  ],
  all_acceptance_bars_met: true,
  hybrid_evaluation: null,
}

export const SESSION_ID = 'sess-0001-aaaa-bbbb-cccc-000000000001'

export const GENERIC_SESSION_LIST_FIXTURE: GenericSessionListResponse = {
  domain: DOMAIN,
  items: [
    { session_id: SESSION_ID, agent_version: 'v2', outcome: 'abandoned', started_at: '2024-01-15T10:00:00Z', detected_mechanisms: ['unnecessary_clarification'], review_status: 'unreviewed' },
  ],
  total: 1, limit: 25, offset: 0,
}

export const GENERIC_SESSION_DETAIL_FIXTURE: GenericSessionDetailResponse = {
  domain: DOMAIN,
  session_id: SESSION_ID,
  outcome: 'abandoned',
  transcript: [
    ['user', 'I need a monitor under $300 with high refresh rate'],
    ['agent', 'Could you clarify your preferred screen size?'],
  ],
  action_sequence: ['understand_query', 'clarify'],
  tool_calls: [
    { tool_name: 'search_products', success: true, error_type: 'none' },
  ],
  failure_attributions: [
    {
      failure_mode: 'unnecessary_clarification', detector_source: 'mock_llm', confidence: 0.9,
      evidence_text: 'Agent asked a clarifying question despite sufficient constraints.',
      review_status: 'unreviewed', corrected_mechanism: null, review_note: null,
      detector_version: 'rule_based_mock-v1', provider: null, model: null, prompt_version: null,
      reviewer: null, reviewed_at: null,
    },
  ],
}

export const GENERIC_MECHANISMS_FIXTURE = {
  domain: DOMAIN,
  mechanisms: [
    { name: 'unnecessary_clarification', source: 'semantic' as const, description: 'Agent asked a clarifying question despite sufficient constraints.' },
    { name: 'retrieval_failure', source: 'deterministic' as const, description: 'No shown candidate satisfies the stated constraints.' },
  ],
}

export const SEGMENT_DIMENSIONS_FIXTURE = {
  domain: DOMAIN,
  dimensions: { platform: ['android', 'ios', 'web'], constraint_count_bucket: ['0-1', '2', '3+'] },
}

export function apiGetMockImpl(path: string, params?: Record<string, string | number | undefined>): Promise<unknown> {
  if (path === '/api/v1/auth/me') return Promise.resolve(ME_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments`) return Promise.resolve(GENERIC_EXPERIMENTS_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/mechanisms`) return Promise.resolve(GENERIC_MECHANISMS_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/segment-dimensions`) return Promise.resolve(SEGMENT_DIMENSIONS_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/metrics`) return Promise.resolve(GENERIC_METRICS_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/guardrails`) return Promise.resolve(GENERIC_GUARDRAILS_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/funnel`) return Promise.resolve(GENERIC_FUNNEL_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/investigation`) {
    return Promise.resolve(genericInvestigationFixture((params?.primary_metric as string) ?? 'abandonment_rate'))
  }
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/ai-quality`) return Promise.resolve(GENERIC_AI_QUALITY_FIXTURE)
  if (path === '/ai-quality/classifier-evaluation') return Promise.resolve(CLASSIFIER_EVALUATION_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/sessions`) return Promise.resolve(GENERIC_SESSION_LIST_FIXTURE)
  if (path.startsWith(`/api/v1/domains/${DOMAIN}/sessions/`)) return Promise.resolve(GENERIC_SESSION_DETAIL_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/config`) return Promise.resolve(PROJECT_CONFIG_FIXTURE)
  if (path === `/api/v1/domains/${DOMAIN}/experiments/${EXPERIMENT_ID}/release-summary`) return Promise.resolve(RELEASE_SUMMARY_FIXTURE)
  return Promise.reject(new Error(`Unmocked path in test: ${path}`))
}

export const RELEASE_SUMMARY_FIXTURE: ReleaseSummaryResponse = {
  decision: {
    evaluation_id: 'eval-0001',
    domain: 'commerce',
    experiment_id: EXPERIMENT_ID,
    primary_metric: 'abandonment_rate',
    verdict: 'ROLLBACK',
    raw_verdict: 'ROLLBACK',
    primary_reason: "Largest excess contribution to the regression is segment 'requested_category=electronics'.",
    primary_metric_v1: 0.2,
    primary_metric_v2: 0.35,
    primary_metric_delta: 0.15,
    primary_metric_p_value: 0.0004,
    breached_guardrails: [{ name: 'p95_latency', severity: 'blocking', v1_value: 1200, v2_value: 2100 }],
    significant_negative_segment_count: 1,
    data_quality_status: 'healthy',
    data_quality_gated: false,
    economics_impact: -0.42,
    confidence: 'strong',
  },
  explanation_text: 'ROLLBACK because abandonment rate increased by 15.0pp and p95 latency breached its blocking guardrail.',
  evidence_hierarchy: [
    { rank: 1, category: 'blocking_guardrail', summary: "Blocking guardrail 'p95_latency' breached (p95 latency increased beyond threshold): v1=1200, v2=2100." },
    { rank: 2, category: 'primary_metric', summary: "Primary metric 'abandonment_rate' regressed by 15.0pp (p=4.00e-04)." },
    { rank: 3, category: 'negative_segment', summary: "Segment 'requested_category=electronics' shows a negative excess contribution of -0.1200 (p=1.00e-05)." },
    { rank: 4, category: 'economics', summary: 'Estimated business impact per session is -0.4200 (negative).' },
    { rank: 5, category: 'failure_mechanism', summary: "Failure mechanism 'retrieval_failure' detected as the dominant contributor in segment 'requested_category=electronics'." },
    { rank: 6, category: 'representative_session', summary: '1 representative session(s) selected across 1 segment(s) for detailed review.' },
  ],
  findings: [
    {
      segment_label: 'requested_category=electronics',
      dimensions: ['requested_category'],
      metric: 'abandonment_rate',
      v1_value: 0.18,
      v2_value: 0.4,
      delta: 0.22,
      p_value: 0.00001,
      excess_contribution: -0.12,
      dominant_failure_mode: 'retrieval_failure',
      representative_session_ids: [SESSION_ID],
      next_action: 'Review retrieval quality for electronics-category queries before expanding rollout.',
    },
  ],
  representative_sessions: [
    {
      session_id: SESSION_ID,
      segment_label: 'requested_category=electronics',
      outcome: 'abandoned',
      transcript_excerpt: [['user', 'I need a monitor under $300'], ['agent', 'Could you clarify your preferred screen size?']],
      action_sequence: ['understand_query', 'clarify'],
      detected_mechanisms: ['retrieval_failure'],
      human_review_status: 'not_reviewed',
      selected_because: "Sampled from the treatment arm, preferring sessions where the detected failure mechanism 'retrieval_failure' was present.",
    },
  ],
  economics: { cost_per_session_v1: 0.5, cost_per_session_v2: 0.6, estimated_business_impact_per_session: -0.42 },
  data_quality_status: 'healthy',
  monitoring_window: { data_window_start: null, data_window_end: null, window_hours: null },
}
