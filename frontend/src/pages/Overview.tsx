import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDomainGuardrails } from '../api/hooks'
import { CIRange } from '../components/common/CIRange'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { GuardrailComparisonChart } from '../components/common/GuardrailComparisonChart'
import { VerdictBadge } from '../components/common/VerdictBadge'
import { formatDelta, formatMetricValue, formatPValue, humanizeMetricName } from '../lib/format'
import { deltaDirection } from '../lib/metricPolarity'
import type { MetricResult } from '../api/types'
import { useActiveExperiment } from '../state/ActiveExperimentContext'
import { useActiveProject } from '../state/ActiveProjectContext'

const STATUS_META: Record<string, { labelKey: string; cls: string }> = {
  ambiguous_investigate: { labelKey: 'overview.statusRequiresInvestigation', cls: 'chip-warning' },
  no_regression_detected: { labelKey: 'overview.statusNoRegression', cls: 'chip-positive' },
  not_yet_investigated: { labelKey: 'overview.statusNotYetInvestigated', cls: 'chip-neutral' },
}

/** The CI is rendered by default here, not hidden behind a "Detail"
 * toggle the way MetricComparisonRow does it (Stage 16 task 4) — the
 * Overview screen's whole purpose is "is this a real difference or
 * noise" at a glance, and a delta chip alone can't answer that. */
function SignalCard({ kicker, metric }: { kicker: string; metric: MetricResult }) {
  const { t } = useTranslation()
  const v1 = metric.cluster_mean_v1
  const v2 = metric.cluster_mean_v2
  const direction = deltaDirection(metric.metric_name, v1, v2)
  const directionCls = direction === 'good' ? 'chip-positive' : direction === 'bad' ? 'chip-negative' : 'chip-neutral'
  return (
    <div className="card">
      <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
        {kicker}
      </div>
      <h3 style={{ marginBottom: 10 }}>{humanizeMetricName(metric.metric_name)}</h3>
      <div style={{ display: 'flex', gap: 18, marginBottom: 10 }}>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v1')}</div>
          <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{formatMetricValue(metric.metric_name, v1)}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v2')}</div>
          <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{formatMetricValue(metric.metric_name, v2)}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>{t('common.delta')}</div>
          <span className={`chip ${directionCls}`}>{formatDelta(metric.metric_name, v1, v2)}</span>
        </div>
      </div>
      <VerdictBadge verdict={metric.verdict} />
      {metric.ci_low !== null && metric.ci_high !== null ? (
        <div style={{ marginTop: 8 }}>
          <CIRange low={metric.ci_low} high={metric.ci_high} formatValue={(v) => formatDelta(metric.metric_name, 0, v)} />
        </div>
      ) : (
        <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>p = {formatPValue(metric.p_value)}</div>
      )}
    </div>
  )
}

/** Stage 16: domain-generic (previously hardcoded to commerce's
 * conversion_rate north star + a hardcoded 'abandonment' investigation
 * lens, neither of which exist as concepts outside the legacy
 * commerce-only API). The north-star card now reads this project's own
 * configured primary_metric (backend already computes it per-experiment
 * in list_domain_experiments); a project that hasn't configured one yet
 * gets a clear prompt to do so instead of a card with no data. The
 * second "AI/product behavior" card from the old two-metric layout is
 * gone -- generically there is only one configured primary metric, so a
 * second card here would just repeat the first. Guardrails are fetched
 * directly (no full Investigation run) since Overview is meant to be
 * cheap; the real Investigation only runs when the user clicks Investigate. */
export function Overview() {
  const { t } = useTranslation()
  const { activeProject } = useActiveProject()
  const { activeExperimentId, activeExperiment, isLoading: expLoading, error: expError } = useActiveExperiment()
  const domain = activeProject?.domain
  const { data: guardrails, isLoading: guardrailsLoading } = useDomainGuardrails(domain, activeProject?.project_id, activeExperimentId ?? undefined)

  if (expLoading) return <div className="page"><LoadingState label={t('overview.loadingExperiments')} /></div>
  if (expError) return <div className="page"><ErrorState error={expError} /></div>
  if (!activeExperiment) {
    return (
      <div className="page">
        <EmptyState>{t('overview.noExperiments')}</EmptyState>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Link to="/project" className="btn btn-primary">{t('overview.checkProjectSetup')}</Link>
        </div>
      </div>
    )
  }

  const statusMeta = STATUS_META[activeExperiment.status_chip]
  const northStar = activeExperiment.north_star_metric

  return (
    <div className="page">
      <div className="page-hero">
        <div className="deco deco-pixels" aria-hidden="true" style={{ width: 150, height: 150, top: -40, right: -30, color: 'var(--color-lime)' }} />
        <div className="page-hero-content">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 6, flexWrap: 'wrap' }}>
            <h1>{activeExperiment.name}</h1>
            <span className={`chip ${statusMeta.cls}`}>{t(statusMeta.labelKey)}</span>
          </div>
          <p className="text-secondary">
            {activeExperiment.control_version} ({t('overview.controlLabel')}) vs {activeExperiment.treatment_version} ({t('overview.treatmentLabel')})
            {activeExperiment.n_users != null && activeExperiment.n_sessions != null && (
              <> · {activeExperiment.n_users.toLocaleString('en-US')} {t('common.users')} · {activeExperiment.n_sessions.toLocaleString('en-US')} {t('common.sessions')}</>
            )}
          </p>
        </div>
      </div>

      {!northStar ? (
        <div className="card">
          <p className="text-secondary">
            {t('overview.noPrimaryMetric')}
          </p>
          <Link to="/setup" className="btn btn-primary" style={{ marginTop: 10 }}>
            {t('overview.configurePrimaryMetric')}
          </Link>
        </div>
      ) : (
        <div className="grid-2">
          <SignalCard kicker={t('overview.primaryMetricKicker')} metric={northStar} />

          <div className="card">
            <h2 style={{ marginBottom: 10 }}>{t('overview.summary')}</h2>
            <p style={{ fontSize: 13.5, lineHeight: 1.7 }}>
              {northStar.verdict === 'significant'
                ? t('overview.movedSignificantly', { metric: humanizeMetricName(northStar.metric_name) })
                : t('overview.flatInconclusive', { metric: humanizeMetricName(northStar.metric_name) })}{' '}
              {guardrails?.any_breach
                ? t('overview.guardrailBreachedSummary', { names: guardrails.checks.filter((g) => g.breached).map((g) => humanizeMetricName(g.name)).join(', ') })
                : t('overview.noGuardrailBreached')}{' '}
              {t('overview.needsSegmentInvestigation')}
            </p>
            <Link to={activeExperimentId ? `/experiments/${activeExperimentId}/investigation` : '#'} className="btn btn-primary" style={{ marginTop: 14 }}>
              {t('overview.investigate')}
            </Link>
          </div>
        </div>
      )}

      {guardrailsLoading && <div className="card"><LoadingState /></div>}
      {guardrails && (
        <div className="card">
          <div className="card-header">
            <h2>{t('overview.guardrails')}</h2>
          </div>
          <h3 style={{ marginBottom: 12 }}>{guardrails.any_breach ? t('overview.breachDetected') : t('overview.allWithinThreshold')}</h3>
          <GuardrailComparisonChart checks={guardrails.checks} />
          {guardrails.checks.length === 0 && <EmptyState>{t('overview.noGuardrailsConfigured')}</EmptyState>}
        </div>
      )}
    </div>
  )
}
