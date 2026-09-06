import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useExperimentDetail, useExperimentFunnel, useExperimentGuardrails, useExperimentMetrics } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { FunnelDiagram } from '../components/common/FunnelDiagram'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import type { SemanticClass } from '../api/types'

const GROUPS: { key: SemanticClass | 'all'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'outcome', label: 'Product outcome' },
  { key: 'post_treatment_mechanism', label: 'Mechanism' },
  { key: 'economic_outcome', label: 'Economics' },
]

export function Experiment() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const [group, setGroup] = useState<(typeof GROUPS)[number]['key']>('all')

  const { data: detail, isLoading: detailLoading, error: detailError } = useExperimentDetail(experimentId)
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useExperimentMetrics(experimentId)
  const { data: funnel, isLoading: funnelLoading, error: funnelError } = useExperimentFunnel(experimentId)
  const { data: guardrails, isLoading: guardrailsLoading, error: guardrailsError } = useExperimentGuardrails(experimentId)

  if (detailLoading) return <div className="page"><LoadingState label="Loading experiment…" /></div>
  if (detailError) return <div className="page"><ErrorState message={(detailError as Error).message} /></div>
  if (!detail) return <div className="page"><EmptyState>Experiment not found.</EmptyState></div>

  const filteredMetrics = metrics?.metrics.filter((m) => group === 'all' || m.semantic_class === group) ?? []

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
            <div style={{ fontSize: 13.5 }}>v1: {detail.n_users_v1.toLocaleString('en-US')} · v2: {detail.n_users_v2.toLocaleString('en-US')}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Sessions</div>
            <div style={{ fontSize: 13.5 }}>v1: {detail.n_sessions_v1.toLocaleString('en-US')} · v2: {detail.n_sessions_v2.toLocaleString('en-US')}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Randomization unit</div>
            <div style={{ fontSize: 13.5 }}>User (each user sees exactly one version for the life of the experiment)</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Status</div>
            <div style={{ fontSize: 13.5 }}>{detail.status}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Traffic split (v2)</div>
            <div style={{ fontSize: 13.5 }}>{(detail.traffic_split * 100).toFixed(0)}%</div>
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
        {metricsError && <ErrorState message={(metricsError as Error).message} />}
        {metrics && filteredMetrics.length === 0 && <EmptyState>No metrics in this group.</EmptyState>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filteredMetrics.map((m) => (
            <MetricComparisonRow key={`${m.metric_name}-${m.segment}`} metric={m} />
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Shopping funnel</h2>
          <p>impression → click → add to cart → purchase</p>
        </div>
        {funnelLoading && <LoadingState />}
        {funnelError && <ErrorState message={(funnelError as Error).message} />}
        {funnel && <FunnelDiagram funnel={funnel.funnel} />}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Guardrails</h2>
          <p>Latency, cost, and tool-error checks that can block a ship decision regardless of the north star.</p>
        </div>
        {guardrailsLoading && <LoadingState />}
        {guardrailsError && <ErrorState message={(guardrailsError as Error).message} />}
        {guardrails && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {guardrails.checks.map((g) => (
              <div
                key={g.name}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px',
                  borderRadius: 6, background: g.breached ? 'var(--color-negative-weak)' : 'var(--color-neutral-weak)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{g.name.replace(/_/g, ' ')}</div>
                  <div className="text-muted" style={{ fontSize: 11.5 }}>{g.threshold_description}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span className="mono text-secondary" style={{ fontSize: 12.5 }}>v1: {g.v1_value.toFixed(3)}</span>
                  <span className="mono text-secondary" style={{ fontSize: 12.5 }}>v2: {g.v2_value.toFixed(3)}</span>
                  <span className={`chip ${g.breached ? 'chip-negative' : 'chip-neutral'}`}>{g.breached ? 'Breached' : 'OK'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
