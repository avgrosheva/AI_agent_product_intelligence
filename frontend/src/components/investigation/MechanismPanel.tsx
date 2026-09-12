import { useTranslation } from 'react-i18next'
import type { Finding, GenericGuardrailCheck, MetricResult } from '../../api/types'
import { ContributionChart, type ContributionRow } from '../common/ContributionChart'
import { formatDelta, formatMetricValue, formatPercent, humanizeSegmentLabel } from '../../lib/format'
import { isAndroidLatencySegment } from '../../lib/knownMechanisms'

const CONTEXT_METRICS = [
  { name: 'clarification_rate', labelKey: 'mechanismPanel.contextClarificationBehavior' },
  { name: 'unnecessary_clarification_rate', labelKey: 'mechanismPanel.contextUnnecessaryClarification' },
  { name: 'time_to_first_recommendation_ms', labelKey: 'mechanismPanel.contextLatencyToFirstRecommendation' },
  { name: 'tool_calls_per_session', labelKey: 'mechanismPanel.contextToolCallsPerSession' },
  { name: 'tool_error_rate', labelKey: 'mechanismPanel.contextToolErrorRate' },
  { name: 'constraint_satisfaction_rate', labelKey: 'mechanismPanel.contextConstraintQuality' },
]

export function MechanismPanel({
  finding, metricsByName, guardrails,
}: {
  finding: Finding
  metricsByName: Record<string, MetricResult>
  guardrails: GenericGuardrailCheck[]
}) {
  const { t } = useTranslation()
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
        <h2>{t('mechanismPanel.mechanism', { segment: humanizeSegmentLabel(finding.segment_label) })}</h2>
        <p>{t('mechanismPanel.associationalOnly')}</p>
      </div>

      {isLatency && (
        <div
          className="card"
          style={{ background: 'var(--color-warning-weak)', borderColor: 'var(--color-warning)', marginBottom: 16, padding: '12px 14px' }}
        >
          <strong style={{ fontSize: 12.5 }}>{t('mechanismPanel.nonConversationalTitle')}</strong>
          <p style={{ fontSize: 12.5, marginTop: 4 }}>
            {t('mechanismPanel.nonConversationalBody')} {p95 && (
              <>{t('mechanismPanel.guardrailStatus', { status: t(p95.breached ? 'mechanismPanel.breached' : 'mechanismPanel.notBreached'), v1: p95.v1_value.toFixed(0), v2: p95.v2_value.toFixed(0) })}</>
            )}{' '}
            {t('mechanismPanel.nonConversationalFooter')}
          </p>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ marginBottom: 10 }}>{t('mechanismPanel.excessAttribution')}</h3>
          {!fa.reportable && (
            <p className="text-muted" style={{ fontSize: 12 }}>
              {t('mechanismPanel.tooSmallToAttribute')}
            </p>
          )}
          {fa.reportable && contributionRows.length > 0 && (
            <>
              <ContributionChart rows={contributionRows} />
              <p className="text-muted" style={{ fontSize: 11, marginTop: 10 }}>
                {t('mechanismPanel.sharesNote', { v1: formatPercent(fa.abandonment_rate_v1), v2: formatPercent(fa.abandonment_rate_v2) })}
              </p>
            </>
          )}
        </div>

        <div style={{ minWidth: 0 }}>
          <h3 style={{ marginBottom: 10 }}>{t('mechanismPanel.trajectoryEvidence')}</h3>
          {finding.trajectory_associations.length === 0 && (
            <p className="text-muted" style={{ fontSize: 12 }}>{t('mechanismPanel.noTrajectoryPattern')}</p>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {finding.trajectory_associations.map((traj) => (
              <div key={traj.pattern} style={{ fontSize: 12 }}>
                <span className="mono" style={{ overflowWrap: 'anywhere' }}>{traj.pattern}</span>
                <div className="text-secondary">
                  {t('mechanismPanel.trajectoryStats', { n: traj.n_sessions, rate: formatPercent(traj.pattern_outcome_rate), baseline: formatPercent(traj.baseline_outcome_rate) })}{' '}
                  {traj.bh_significant ? <span className="chip chip-accent" style={{ marginLeft: 4 }}>{t('mechanismPanel.bhSignificant')}</span> : <span className="text-muted">{t('mechanismPanel.notSignificantAfterCorrection')}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--color-border)' }}>
        <h3 style={{ marginBottom: 4 }}>{t('mechanismPanel.experimentWideContext')}</h3>
        <p className="text-muted" style={{ fontSize: 11, marginBottom: 10 }}>
          {t('mechanismPanel.experimentWideContextSub')}
        </p>
        <div className="grid-3">
          {CONTEXT_METRICS.map(({ name, labelKey }) => {
            const m = metricsByName[name]
            if (!m) return null
            return (
              <div key={name} style={{ fontSize: 12 }}>
                <div className="text-muted" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.03em' }}>{t(labelKey)}</div>
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
