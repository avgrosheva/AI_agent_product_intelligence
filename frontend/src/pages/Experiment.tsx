import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDomainFunnel, useDomainGuardrails, useDomainMetrics } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { FunnelDiagram } from '../components/common/FunnelDiagram'
import { GuardrailComparisonChart } from '../components/common/GuardrailComparisonChart'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import type { SemanticClass } from '../api/types'
import { useActiveExperiment } from '../state/ActiveExperimentContext'
import { useActiveProject } from '../state/ActiveProjectContext'

const GROUPS: { key: SemanticClass | 'all'; labelKey: string }[] = [
  { key: 'all', labelKey: 'experiment.groupAll' },
  { key: 'outcome', labelKey: 'experiment.groupOutcome' },
  { key: 'post_treatment_mechanism', labelKey: 'experiment.groupMechanism' },
  { key: 'economic_outcome', labelKey: 'experiment.groupEconomics' },
]

/** Stage 16: domain-generic (previously called commerce-only,
 * project-unscoped endpoints). Experiment identity (name/versions) comes
 * from the already-loaded, project-scoped experiments list
 * (ActiveExperimentContext) rather than a separate detail call; per-arm
 * session/user counts come from the metrics table's own rows (every
 * MetricResult already carries n_sessions_v1/v2 and n_users_v1/v2) since
 * the generic API has no separate "experiment detail" endpoint --
 * traffic_split/status are commerce-specific columns with no generic
 * equivalent and are dropped rather than faked. */
export function Experiment() {
  const { t } = useTranslation()
  const { experimentId } = useParams<{ experimentId: string }>()
  const [group, setGroup] = useState<(typeof GROUPS)[number]['key']>('all')
  const { activeProject } = useActiveProject()
  const { experiments, isLoading: expListLoading, error: expListError } = useActiveExperiment()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id

  const detail = experiments.find((e) => e.experiment_id === experimentId) ?? null
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDomainMetrics(domain, projectId, experimentId)
  const { data: funnel, isLoading: funnelLoading, error: funnelError } = useDomainFunnel(domain, projectId, experimentId)
  const { data: guardrails, isLoading: guardrailsLoading, error: guardrailsError } = useDomainGuardrails(domain, projectId, experimentId)

  if (expListLoading) return <div className="page"><LoadingState label={t('experiment.loadingExperiment')} /></div>
  if (expListError) return <div className="page"><ErrorState error={expListError} /></div>
  if (!detail) return <div className="page"><EmptyState>{t('experiment.notFound')}</EmptyState></div>

  const filteredMetrics = metrics?.metrics.filter((m) => group === 'all' || m.semantic_class === group) ?? []
  const firstMetric = metrics?.metrics[0]

  return (
    <div className="page">
      <div>
        <h1>{detail.name}</h1>
        <p className="text-secondary">{t('experiment.fullReadout')}</p>
      </div>

      <div className="card">
        <h2 style={{ marginBottom: 14 }}>{t('experiment.metadata')}</h2>
        <div className="grid-3">
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('experiment.versions')}</div>
            <div style={{ fontSize: 13.5 }}>{detail.control_version} (v1) vs {detail.treatment_version} (v2)</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('experiment.usersLabel')}</div>
            <div style={{ fontSize: 13.5 }}>
              {firstMetric ? <>v1: {firstMetric.n_users_v1.toLocaleString('en-US')} · v2: {firstMetric.n_users_v2.toLocaleString('en-US')}</> : '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('experiment.sessionsLabel')}</div>
            <div style={{ fontSize: 13.5 }}>
              {firstMetric ? <>v1: {firstMetric.n_sessions_v1.toLocaleString('en-US')} · v2: {firstMetric.n_sessions_v2.toLocaleString('en-US')}</> : '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('experiment.randomizationUnit')}</div>
            <div style={{ fontSize: 13.5 }}>{t('experiment.randomizationUnitValue')}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('experiment.startEnd')}</div>
            <div style={{ fontSize: 13.5 }}>{detail.start_date ?? '—'} → {detail.end_date ?? '—'}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('experiment.metricComparison')}</h2>
          <p>{t('experiment.metricComparisonSub')}</p>
        </div>
        <div className="tabs" style={{ marginBottom: 14 }}>
          {GROUPS.map((g) => (
            <button key={g.key} type="button" className={`tab${group === g.key ? ' active' : ''}`} onClick={() => setGroup(g.key)}>
              {t(g.labelKey)}
            </button>
          ))}
        </div>
        {metricsLoading && <LoadingState label={t('experiment.computingMetricTable')} />}
        {metricsError && <ErrorState error={metricsError} />}
        {metrics && filteredMetrics.length === 0 && <EmptyState>{t('experiment.noMetricsInGroup')}</EmptyState>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filteredMetrics.map((m) => (
            <MetricComparisonRow key={`${m.metric_name}-${m.segment}`} metric={m} />
          ))}
        </div>
      </div>

      {(funnelLoading || funnelError || funnel?.applicable) && (
        <div className="card">
          <div className="card-header">
            <h2>{t('experiment.funnel')}</h2>
            <p>{t('experiment.funnelSub')}</p>
          </div>
          {funnelLoading && <LoadingState />}
          {funnelError && <ErrorState error={funnelError} />}
          {funnel?.applicable && <FunnelDiagram series={funnel.series} />}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h2>{t('experiment.guardrails')}</h2>
          <p>{t('experiment.guardrailsSub')}</p>
        </div>
        {guardrailsLoading && <LoadingState />}
        {guardrailsError && <ErrorState error={guardrailsError} />}
        {guardrails && (
          <>
            <GuardrailComparisonChart checks={guardrails.checks} />
            {guardrails.checks.length === 0 && <EmptyState>{t('experiment.noGuardrailsConfigured')}</EmptyState>}
          </>
        )}
      </div>
    </div>
  )
}
