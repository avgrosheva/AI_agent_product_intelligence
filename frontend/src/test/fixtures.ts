import type {
  AIQualitySummaryResponse,
  ClassifierEvaluationResponse,
  ExperimentDetail,
  ExperimentListResponse,
  FunnelResponse,
  GuardrailResponse,
  InvestigationResponse,
  MetricResult,
  MetricTableResponse,
  SessionDetail,
  SessionListResponse,
} from '../api/types'

export const EXPERIMENT_ID = 'exp-1234'

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

export const EXPERIMENTS_FIXTURE: ExperimentListResponse = {
  experiments: [
    {
      experiment_id: EXPERIMENT_ID,
      name: 'Conversational Agent v2 Rollout',
      control_version: 'v1',
      treatment_version: 'v2',
      start_date: '2024-01-01',
      end_date: '2024-02-01',
      status: 'completed',
      n_sessions: 32299,
      n_users: 9000,
      north_star_metric: metric(),
      status_chip: 'ambiguous_investigate',
    },
  ],
}

export const EXPERIMENT_DETAIL_FIXTURE: ExperimentDetail = {
  experiment_id: EXPERIMENT_ID,
  name: 'Conversational Agent v2 Rollout',
  control_version: 'v1',
  treatment_version: 'v2',
  start_date: '2024-01-01',
  end_date: '2024-02-01',
  status: 'completed',
  traffic_split: 0.5,
  n_sessions_v1: 16188,
  n_sessions_v2: 16111,
  n_users_v1: 4542,
  n_users_v2: 4458,
}

export const METRICS_FIXTURE: MetricTableResponse = {
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

export const FUNNEL_FIXTURE: FunnelResponse = {
  experiment_id: EXPERIMENT_ID,
  funnel: [
    { agent_version: 'v1', n_sessions: 16188, n_impression: 12000, n_click: 6300, n_cart: 4586, n_purchase: 3181, impression_to_click_rate: 0.525, click_to_cart_rate: 0.648, cart_to_purchase_rate: 0.694 },
    { agent_version: 'v2', n_sessions: 16111, n_impression: 11500, n_click: 6000, n_cart: 4287, n_purchase: 2986, impression_to_click_rate: 0.521, click_to_cart_rate: 0.655, cart_to_purchase_rate: 0.697 },
  ],
}

export const GUARDRAILS_FIXTURE: GuardrailResponse = {
  experiment_id: EXPERIMENT_ID,
  any_breach: true,
  checks: [
    { name: 'p95_latency', v1_value: 2187.65, v2_value: 2954.0, threshold_description: 'v2 p95 latency must not exceed v1 by more than 15%', breached: true },
    { name: 'tool_error_rate', v1_value: 0.068, v2_value: 0.064, threshold_description: 'v2 tool error rate must not exceed v1 by more than 2pp', breached: false },
    { name: 'cost_per_session', v1_value: 0.0052, v2_value: 0.0053, threshold_description: 'v2 cost must not exceed v1 by more than 20%', breached: false },
  ],
}

export function investigationFixture(lens: 'abandonment' | 'conversion' | 'constraint_satisfaction' = 'abandonment'): InvestigationResponse {
  return {
    experiment_id: EXPERIMENT_ID,
    lens,
    lens_role: 'primary_regression_lens',
    lens_description: 'Primary Investigation lens for the current flagship experiment.',
    primary_metric: 'abandonment_rate',
    overall: metric({ metric_name: 'abandonment_rate', cluster_mean_v1: 0.169, cluster_mean_v2: 0.219, p_value: 8.5e-23, verdict: 'significant' }),
    guardrails: GUARDRAILS_FIXTURE.checks,
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

export const AI_QUALITY_FIXTURE: AIQualitySummaryResponse = {
  experiment_id: EXPERIMENT_ID,
  failure_mode_distribution: [
    { failure_mode: 'unnecessary_clarification', count_v1: 100, count_v2: 400, rate_v1: 0.02, rate_v2: 0.09 },
    { failure_mode: 'none', count_v1: 4000, count_v2: 3800, rate_v1: 0.88, rate_v2: 0.85 },
  ],
  tool_use_quality: {
    tool_calls_per_session_v1: 1.89, tool_calls_per_session_v2: 1.85,
    tool_success_rate_v1: 0.93, tool_success_rate_v2: 0.94,
    tool_error_rate_v1: 0.068, tool_error_rate_v2: 0.064,
  },
  trajectory_patterns: [
    { pattern: 'exact:understand_query>search>recommend', n_sessions_v1: 4000, n_sessions_v2: 3900, abandonment_rate_v1: 0.15, abandonment_rate_v2: 0.16 },
  ],
  classifier_provenance: {
    classifier_type: 'rule_based_mock',
    classifier_version: 'rule_based_mock-v1',
    is_mock: true,
    evaluation_status: 'evaluated_current',
    run_at: '2024-02-01T00:00:00Z',
  },
}

export const CLASSIFIER_EVALUATION_FIXTURE: ClassifierEvaluationResponse = {
  provenance: AI_QUALITY_FIXTURE.classifier_provenance,
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
}

export const SESSION_LIST_FIXTURE: SessionListResponse = {
  items: [
    {
      session_id: 'sess-0001-aaaa-bbbb-cccc-000000000001',
      agent_version: 'v2', requested_category: 'monitor', constraint_count_bucket: '3+', platform: 'android',
      device_tier: 'mid', locale: 'en-US', persona: 'mainstream', outcome: 'abandoned', num_turns: 4,
      total_latency_ms: 3200, total_cost_usd: 0.0061, started_at: '2024-01-15T10:00:00Z', failure_mode: 'unnecessary_clarification',
    },
  ],
  total: 1, limit: 25, offset: 0, filters_applied: { constraint_count_bucket: '3+' },
}

export function apiGetMockImpl(path: string, params?: Record<string, string | number | undefined>): Promise<unknown> {
  if (path === '/experiments') return Promise.resolve(EXPERIMENTS_FIXTURE)
  if (path === `/experiments/${EXPERIMENT_ID}`) return Promise.resolve(EXPERIMENT_DETAIL_FIXTURE)
  if (path === `/experiments/${EXPERIMENT_ID}/metrics`) return Promise.resolve(METRICS_FIXTURE)
  if (path === `/experiments/${EXPERIMENT_ID}/funnel`) return Promise.resolve(FUNNEL_FIXTURE)
  if (path === `/experiments/${EXPERIMENT_ID}/guardrails`) return Promise.resolve(GUARDRAILS_FIXTURE)
  if (path === `/experiments/${EXPERIMENT_ID}/investigation`) {
    const lens = (params?.lens as 'abandonment' | 'conversion' | 'constraint_satisfaction') ?? 'abandonment'
    return Promise.resolve(investigationFixture(lens))
  }
  if (path === `/experiments/${EXPERIMENT_ID}/ai-quality`) return Promise.resolve(AI_QUALITY_FIXTURE)
  if (path === '/ai-quality/classifier-evaluation') return Promise.resolve(CLASSIFIER_EVALUATION_FIXTURE)
  if (path === '/sessions') return Promise.resolve(SESSION_LIST_FIXTURE)
  if (path.startsWith('/sessions/')) return Promise.resolve(SESSION_DETAIL_FIXTURE)
  return Promise.reject(new Error(`Unmocked path in test: ${path}`))
}

export const SESSION_DETAIL_FIXTURE: SessionDetail = {
  session_id: 'sess-0001-aaaa-bbbb-cccc-000000000001',
  agent_version: 'v2', requested_category: 'monitor', constraint_count_bucket: '3+', platform: 'android',
  device_tier: 'mid', locale: 'en-US', persona: 'mainstream', num_constraints: 3, outcome: 'abandoned', num_turns: 4,
  total_latency_ms: 3200, total_tokens_in: 500, total_tokens_out: 300, total_cost_usd: 0.0061,
  started_at: '2024-01-15T10:00:00Z', ended_at: '2024-01-15T10:02:00Z',
  transcript: [
    { turn_index: 1, sender: 'user', text: 'I need a monitor under $300 with high refresh rate', tokens: 12, latency_ms: null, created_at: '2024-01-15T10:00:00Z' },
    { turn_index: 1, sender: 'agent', text: 'Could you clarify your preferred screen size?', tokens: 10, latency_ms: 900, created_at: '2024-01-15T10:00:05Z' },
  ],
  agent_actions: [
    { sequence_index: 0, action_type: 'understand_query', latency_ms: 400, model_name: 'agent-v2', started_at: '2024-01-15T10:00:01Z' },
    { sequence_index: 1, action_type: 'clarify', latency_ms: 300, model_name: 'agent-v2', started_at: '2024-01-15T10:00:04Z' },
  ],
  tool_calls: [
    { tool_name: 'search_products', success: true, error_type: 'none', latency_ms: 250, action_sequence_index: 0, action_started_at: '2024-01-15T10:00:01Z' },
  ],
  recommendations: [
    { product_id: 'prod-0001', rank_position: 1, clicked: false, satisfies_constraints: true },
  ],
  product_events: [
    { event_type: 'impression', event_time: '2024-01-15T10:00:02Z', price_at_event: 25000 },
  ],
  evaluations: [
    { eval_type: 'offline_task_success', score: 0, evaluator: 'deterministic_rule' },
  ],
  failure_classification: {
    failure_mode: 'unnecessary_clarification', confidence: 0.9, evidence_text: 'Agent asked a clarifying question despite sufficient constraints.',
    source: 'llm_classifier',
    provenance: AI_QUALITY_FIXTURE.classifier_provenance,
  },
}
