import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDomainInvestigation, useDomainMetrics, useProjectConfig } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { RecommendationPanel } from '../components/common/RecommendationPanel'
import { SegmentEffectChart } from '../components/common/SegmentEffectChart'
import { FindingCard, findingHeadline } from '../components/investigation/FindingCard'
import { MechanismPanel } from '../components/investigation/MechanismPanel'
import { ExploredSegmentsTable } from '../components/investigation/ExploredSegmentsTable'
import { formatDelta, formatMetricValue, formatPValue, humanizeMetricName } from '../lib/format'
import type { MetricResult } from '../api/types'
import { useActiveProject } from '../state/ActiveProjectContext'

/** Stage 16: domain-generic. Previously drove three hardcoded commerce
 * "lenses" (abandonment/conversion/constraint_satisfaction) against the
 * commerce-only /investigation endpoint; the generic investigation API
 * has no lens concept, just a primary_metric. Defaults to this project's
 * configured primary_metric (the same one the Overview north-star card
 * and release evaluations use), with a dropdown over the domain's other
 * implemented, inferential metrics for exploring a different one. */
export function Investigation() {
  const { t } = useTranslation()
  const { experimentId } = useParams<{ experimentId: string }>()
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: config } = useProjectConfig(domain, projectId)
  const metricFromUrl = searchParams.get('metric')
  const metric = metricFromUrl ?? config?.primary_metric ?? undefined
  const [selectedIndex, setSelectedIndex] = useState(0)

  const { data: inv, isLoading, error } = useDomainInvestigation(domain, projectId, experimentId, metric)
  const { data: metricsTable } = useDomainMetrics(domain, projectId, experimentId)

  // Stage 17 task 2: curated by default, not every implemented
  // inferential metric a domain happens to have (commerce alone
  // registers ~15+) -- prioritizes the primary metric, every metric a
  // configured guardrail watches, and (when this project has customized
  // its own metrics config rather than using the domain's static
  // defaults) every metric that customization explicitly kept. The
  // currently-active metric is always included even if none of the
  // above would have surfaced it (e.g. a deep link), so a tab is never
  // missing for whatever's actually selected. The full list stays one
  // click away, never the default.
  const allInferentialMetrics = useMemo(() => (config?.available_metrics ?? []).filter((m) => m.is_inferential), [config])
  const curatedMetricNames = useMemo(() => {
    const names = new Set<string>()
    if (config?.primary_metric) names.add(config.primary_metric)
    for (const g of config?.available_guardrails ?? []) {
      if (g.metric) names.add(g.metric)
    }
    if (config?.metrics) {
      for (const m of config.metrics.metrics) names.add(m.name)
    }
    if (metric) names.add(metric)
    return names
  }, [config, metric])
  const curatedMetrics = useMemo(
    () => allInferentialMetrics.filter((m) => curatedMetricNames.has(m.name)),
    [allInferentialMetrics, curatedMetricNames],
  )
  const [showAllMetrics, setShowAllMetrics] = useState(false)
  const visibleMetrics = showAllMetrics ? allInferentialMetrics : curatedMetrics
  const hasMoreMetrics = allInferentialMetrics.length > curatedMetrics.length

  useEffect(() => {
    setSelectedIndex(0)
  }, [metric])

  const metricsByName = useMemo(() => {
    const map: Record<string, MetricResult> = {}
    metricsTable?.metrics.forEach((m) => { map[m.metric_name] = m })
    return map
  }, [metricsTable])

  function setMetric(next: string) {
    setSearchParams({ metric: next })
  }

  if (!experimentId) return <div className="page"><EmptyState>{t('investigation.noActiveExperiment')}</EmptyState></div>
  if (!metric) {
    return (
      <div className="page">
        <EmptyState>
          {t('investigation.noPrimaryMetricConfigured')}
        </EmptyState>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-hero">
        <div className="deco deco-blob" aria-hidden="true" style={{ width: 130, height: 130, top: -50, right: 40, background: 'var(--color-accent)', opacity: 0.35 }} />
        <div className="page-hero-content">
          <h1>{t('investigation.title')}</h1>
          <p className="text-secondary">{t('investigation.subtitle')}</p>
        </div>
      </div>

      {visibleMetrics.length > 1 && (
        <div className="tabs" style={{ alignItems: 'center', overflowX: 'auto', flexWrap: 'nowrap' }}>
          {visibleMetrics.map((m) => (
            <button key={m.name} type="button" className={`tab${metric === m.name ? ' active' : ''}`} onClick={() => setMetric(m.name)}>
              {m.label || humanizeMetricName(m.name)}
            </button>
          ))}
          {hasMoreMetrics && (
            <button
              type="button"
              className="btn btn-small"
              style={{ marginLeft: 8, flexShrink: 0 }}
              onClick={() => setShowAllMetrics((v) => !v)}
            >
              {showAllMetrics ? t('investigation.showFewer') : t('investigation.showAllMetrics', { count: allInferentialMetrics.length })}
            </button>
          )}
        </div>
      )}

      {isLoading && <LoadingState label={t('investigation.runningInvestigation', { metric })} />}
      {error && <ErrorState error={error} />}

      {inv && (
        <>
          <div className="card">
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              {t('investigation.primaryRegressionSignal')}
            </div>
            <h2 style={{ marginBottom: 8 }}>{findingHeadline(metric, inv.findings[0])}</h2>
            {inv.findings[0] && (
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13 }}>
                <span>v1 {formatMetricValue(inv.primary_metric, inv.findings[0].cluster_mean_v1)} → v2 {formatMetricValue(inv.primary_metric, inv.findings[0].cluster_mean_v2)}</span>
                <span>{t('investigation.deltaLabel', { value: formatDelta(inv.primary_metric, inv.findings[0].cluster_mean_v1, inv.findings[0].cluster_mean_v2) })}</span>
                <span>p = {formatPValue(inv.findings[0].p_value)}</span>
                <span>{t('investigation.excessContribution', { value: (inv.findings[0].excess_contribution * 100).toFixed(1) })}</span>
              </div>
            )}
          </div>

          {inv.findings.length > 1 && (
            <div className="card">
              <div className="card-header">
                <h2>{t('investigation.excessContributionBySegment')}</h2>
                <p>{t('investigation.excessContributionSub')}</p>
              </div>
              <SegmentEffectChart rows={inv.findings.map((f) => ({ segment_label: f.segment_label, excess_contribution: f.excess_contribution }))} />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 20, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <h3>{t('investigation.rankedFindings', { count: inv.findings.length })}</h3>
              {inv.findings.length === 0 && <EmptyState>{t('investigation.noSegmentPassed')}</EmptyState>}
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
