import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useExperimentMetrics, useInvestigation } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { RecommendationPanel } from '../components/common/RecommendationPanel'
import { FindingCard, lensHeadline } from '../components/investigation/FindingCard'
import { MechanismPanel } from '../components/investigation/MechanismPanel'
import { ExploredSegmentsTable } from '../components/investigation/ExploredSegmentsTable'
import { formatDelta, formatMetricValue, formatPValue } from '../lib/format'
import type { InvestigationLens, MetricResult } from '../api/types'

const LENSES: { key: InvestigationLens; label: string }[] = [
  { key: 'abandonment', label: 'Abandonment' },
  { key: 'conversion', label: 'Conversion' },
  { key: 'constraint_satisfaction', label: 'Constraint satisfaction' },
]

export function Investigation() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const lens = (searchParams.get('lens') as InvestigationLens) || 'abandonment'
  const [selectedIndex, setSelectedIndex] = useState(0)

  const { data: inv, isLoading, error } = useInvestigation(experimentId, lens)
  const { data: metricsTable } = useExperimentMetrics(experimentId)

  useEffect(() => {
    setSelectedIndex(0)
  }, [lens])

  const metricsByName = useMemo(() => {
    const map: Record<string, MetricResult> = {}
    metricsTable?.metrics.forEach((m) => { map[m.metric_name] = m })
    return map
  }, [metricsTable])

  function setLens(next: InvestigationLens) {
    setSearchParams({ lens: next })
  }

  if (!experimentId) return <div className="page"><EmptyState>No active experiment selected.</EmptyState></div>

  return (
    <div className="page">
      <div>
        <h1>Investigation</h1>
        <p className="text-secondary">Where is the regression concentrated, and what behavior is associated with it?</p>
      </div>

      <div className="tabs">
        {LENSES.map((l) => (
          <button key={l.key} type="button" className={`tab${lens === l.key ? ' active' : ''}`} onClick={() => setLens(l.key)}>
            {l.label}
          </button>
        ))}
      </div>

      {isLoading && <LoadingState label={`Running ${lens} investigation…`} />}
      {error && <ErrorState message={(error as Error).message} />}

      {inv && (
        <>
          <div className="card">
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              {inv.lens_role.replace(/_/g, ' ')}
            </div>
            <h2 style={{ marginBottom: 8 }}>{lensHeadline(lens, inv.findings[0])}</h2>
            <p className="text-secondary" style={{ fontSize: 12.5, marginBottom: 12 }}>{inv.lens_description}</p>
            {inv.findings[0] && (
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13 }}>
                <span>v1 {formatMetricValue(inv.primary_metric, inv.findings[0].cluster_mean_v1)} → v2 {formatMetricValue(inv.primary_metric, inv.findings[0].cluster_mean_v2)}</span>
                <span>delta {formatDelta(inv.primary_metric, inv.findings[0].cluster_mean_v1, inv.findings[0].cluster_mean_v2)}</span>
                <span>p = {formatPValue(inv.findings[0].p_value)}</span>
                <span>excess contribution {(inv.findings[0].excess_contribution * 100).toFixed(1)}%</span>
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 20, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <h3>Ranked findings ({inv.findings.length})</h3>
              {inv.findings.length === 0 && <EmptyState>No segment passed correction and minimum-effect-size filtering for this lens.</EmptyState>}
              {inv.findings.map((f, i) => (
                <FindingCard
                  key={f.segment_label}
                  finding={f}
                  metricName={inv.primary_metric}
                  experimentId={experimentId}
                  selected={i === selectedIndex}
                  onSelect={() => setSelectedIndex(i)}
                />
              ))}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {inv.findings[selectedIndex] && (
                <MechanismPanel finding={inv.findings[selectedIndex]} metricsByName={metricsByName} guardrails={inv.guardrails} />
              )}
              <RecommendationPanel recommendation={inv.recommendation} />
            </div>
          </div>

          <ExploredSegmentsTable segments={inv.explored_not_significant} />
        </>
      )}
    </div>
  )
}
