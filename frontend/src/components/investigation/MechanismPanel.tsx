import type { Finding, GenericGuardrailCheck, MetricResult } from '../../api/types'
import { ContributionChart, type ContributionRow } from '../common/ContributionChart'
import { formatDelta, formatMetricValue, formatPercent, humanizeSegmentLabel } from '../../lib/format'
import { isAndroidLatencySegment } from '../../lib/knownMechanisms'

const CONTEXT_METRICS = [
  { name: 'clarification_rate', label: 'Clarification behavior' },
  { name: 'unnecessary_clarification_rate', label: 'Unnecessary clarification' },
  { name: 'time_to_first_recommendation_ms', label: 'Latency to first recommendation' },
  { name: 'tool_calls_per_session', label: 'Tool calls per session' },
  { name: 'tool_error_rate', label: 'Tool error rate' },
  { name: 'constraint_satisfaction_rate', label: 'Constraint quality' },
]

export function MechanismPanel({
  finding, metricsByName, guardrails,
}: {
  finding: Finding
  metricsByName: Record<string, MetricResult>
  guardrails: GenericGuardrailCheck[]
}) {
  const isLatency = isAndroidLatencySegment(finding)
  const fa = finding.failure_attribution
  const p95 = guardrails.find((g) => g.name === 'p95_latency')

  const contributionRows: ContributionRow[] = fa.reportable
    ? fa.per_mode
        .filter((m) => m.share_of_excess_abandonment !== null || m.excess_count !== 0)
        .map((m) => ({ label: m.failure_mode.replace(/_/g, ' '), share: m.share_of_excess_abandonment }))
    : []

  return (
    <div className="card">
      <div className="card-header">
        <h2>Mechanism: {humanizeSegmentLabel(finding.segment_label)}</h2>
        <p>Associational evidence only — never a causal claim for post-treatment behavior.</p>
      </div>

      {isLatency && (
        <div
          className="card"
          style={{ background: 'var(--color-warning-weak)', borderColor: 'var(--color-warning)', marginBottom: 16, padding: '12px 14px' }}
        >
          <strong style={{ fontSize: 12.5 }}>Non-conversational mechanism: elevated Android latency.</strong>
          <p style={{ fontSize: 12.5, marginTop: 4 }}>
            This segment's regression is associated with an Android-platform latency regression, not a conversational
            failure mode. {p95 && (
              <>The experiment-wide p95 latency guardrail is {p95.breached ? 'breached' : 'not breached'} (v1 {p95.v1_value.toFixed(0)}ms vs v2 {p95.v2_value.toFixed(0)}ms).</>
            )}{' '}
            The classifier's dominant failure-mode label below (if any) is a secondary, incidental conversational-taxonomy
            signal for this segment — it does not explain the regression. Open the affected sessions to see real per-session latency.
          </p>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <h3 style={{ marginBottom: 10 }}>Excess-abandonment attribution (segment-specific)</h3>
          {!fa.reportable && (
            <p className="text-muted" style={{ fontSize: 12 }}>
              Total excess abandonment in this segment is too small to attribute a reliable per-mode share.
            </p>
          )}
          {fa.reportable && contributionRows.length > 0 && (
            <>
              <ContributionChart rows={contributionRows} />
              <p className="text-muted" style={{ fontSize: 11, marginTop: 10 }}>
                Shares may exceed 100% or be negative (offsetting contributions) — not clamped or renormalized.
                Abandonment: v1 {formatPercent(fa.abandonment_rate_v1)} → v2 {formatPercent(fa.abandonment_rate_v2)}.
              </p>
            </>
          )}
        </div>

        <div>
          <h3 style={{ marginBottom: 10 }}>Trajectory evidence (segment-specific)</h3>
          {finding.trajectory_associations.length === 0 && (
            <p className="text-muted" style={{ fontSize: 12 }}>No trajectory pattern reached the minimum session count in this segment.</p>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {finding.trajectory_associations.map((t) => (
              <div key={t.pattern} style={{ fontSize: 12 }}>
                <span className="mono">{t.pattern}</span>
                <div className="text-secondary">
                  n={t.n_sessions} · outcome rate {formatPercent(t.pattern_outcome_rate)} vs baseline {formatPercent(t.baseline_outcome_rate)}{' '}
                  {t.bh_significant ? <span className="chip chip-accent" style={{ marginLeft: 4 }}>co-occurs with outcome (BH-significant)</span> : <span className="text-muted">(not significant after correction)</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--color-border)' }}>
        <h3 style={{ marginBottom: 4 }}>Experiment-wide mechanism context</h3>
        <p className="text-muted" style={{ fontSize: 11, marginBottom: 10 }}>
          Not segment-specific — shown for context on the kind of behavior associated with v2 overall.
        </p>
        <div className="grid-3">
          {CONTEXT_METRICS.map(({ name, label }) => {
            const m = metricsByName[name]
            if (!m) return null
            return (
              <div key={name} style={{ fontSize: 12 }}>
                <div className="text-muted" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.03em' }}>{label}</div>
                <div>
                  {formatMetricValue(name, m.cluster_mean_v1)} → {formatMetricValue(name, m.cluster_mean_v2)}{' '}
                  <span className="text-secondary">({formatDelta(name, m.cluster_mean_v1, m.cluster_mean_v2)})</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
