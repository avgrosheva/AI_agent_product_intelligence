import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useDomainFunnel, useDomainGuardrails, useDomainMetrics } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { FunnelDiagram } from '../components/common/FunnelDiagram'
import { GuardrailComparisonChart } from '../components/common/GuardrailComparisonChart'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import type { SemanticClass } from '../api/types'
import { useActiveExperiment } from '../state/ActiveExperimentContext'
import { useActiveProject } from '../state/ActiveProjectContext'

const GROUPS: { key: SemanticClass | 'all'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'outcome', label: 'Product outcome' },
  { key: 'post_treatment_mechanism', label: 'Mechanism' },
  { key: 'economic_outcome', label: 'Economics' },
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

  if (expListLoading) return <div className="page"><LoadingState label="Loading experiment…" /></div>
  if (expListError) return <div className="page"><ErrorState error={expListError} /></div>
  if (!detail) return <div className="page"><EmptyState>Experiment not found.</EmptyState></div>

  const filteredMetrics = metrics?.metrics.filter((m) => group === 'all' || m.semantic_class === group) ?? []
  const firstMetric = metrics?.metrics[0]

  return (
    <div className="page">
      <div>
        <h1>{detail.name}</h1>
        <p className="text-secondary">Full experiment readout</p>
      </div>

      <div className="card">
        <h2 style={{ marginBottom: 14 }}>Experiment metadata</h2>
        <div className="grid-3">
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Versions</div>
            <div style={{ fontSize: 13.5 }}>{detail.control_version} (v1) vs {detail.treatment_version} (v2)</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Users</div>
            <div style={{ fontSize: 13.5 }}>
              {firstMetric ? <>v1: {firstMetric.n_users_v1.toLocaleString('en-US')} · v2: {firstMetric.n_users_v2.toLocaleString('en-US')}</> : '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Sessions</div>
            <div style={{ fontSize: 13.5 }}>
              {firstMetric ? <>v1: {firstMetric.n_sessions_v1.toLocaleString('en-US')} · v2: {firstMetric.n_sessions_v2.toLocaleString('en-US')}</> : '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Randomization unit</div>
            <div style={{ fontSize: 13.5 }}>User (each user sees exactly one version for the life of the experiment)</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Start / end</div>
            <div style={{ fontSize: 13.5 }}>{detail.start_date ?? '—'} → {detail.end_date ?? '—'}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Metric comparison</h2>
          <p>Every number is computed server-side; statistical detail is available per row.</p>
        </div>
        <div className="tabs" style={{ marginBottom: 14 }}>
          {GROUPS.map((g) => (
            <button key={g.key} type="button" className={`tab${group === g.key ? ' active' : ''}`} onClick={() => setGroup(g.key)}>
              {g.label}
            </button>
          ))}
        </div>
        {metricsLoading && <LoadingState label="Computing metric table…" />}
        {metricsError && <ErrorState error={metricsError} />}
        {metrics && filteredMetrics.length === 0 && <EmptyState>No metrics in this group.</EmptyState>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filteredMetrics.map((m) => (
            <MetricComparisonRow key={`${m.metric_name}-${m.segment}`} metric={m} />
          ))}
        </div>
      </div>

      {(funnelLoading || funnelError || funnel?.applicable) && (
        <div className="card">
          <div className="card-header">
            <h2>Funnel</h2>
            <p>Ordered stages this domain's sessions pass through.</p>
          </div>
          {funnelLoading && <LoadingState />}
          {funnelError && <ErrorState error={funnelError} />}
          {funnel?.applicable && <FunnelDiagram series={funnel.series} />}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h2>Guardrails</h2>
          <p>Latency, cost, and error checks that can block a ship decision regardless of the north star.</p>
        </div>
        {guardrailsLoading && <LoadingState />}
        {guardrailsError && <ErrorState error={guardrailsError} />}
        {guardrails && (
          <>
            <GuardrailComparisonChart checks={guardrails.checks} />
            {guardrails.checks.length === 0 && <EmptyState>No guardrails configured.</EmptyState>}
          </>
        )}
      </div>
    </div>
  )
}
