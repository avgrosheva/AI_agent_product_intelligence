import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useCreateReleaseEvaluation, useReleaseHistory, useReleaseSummary } from '../api/hooks'
import { ApiError } from '../api/client'
import type { DataQualityStatus, ReleaseVerdict } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { ReleaseTrendChart } from '../components/common/ReleaseTrendChart'
import { SegmentEffectChart } from '../components/common/SegmentEffectChart'
import { formatDateTime, formatPValue, humanizeMetricName, humanizeSegmentLabel } from '../lib/format'
import { useActiveProject } from '../state/ActiveProjectContext'

const VERDICT_CLASS: Record<ReleaseVerdict, string> = {
  SHIP: 'chip-positive',
  HOLD: 'chip-warning',
  ROLLBACK: 'chip-negative',
}

const VERDICT_HERO_BG: Record<ReleaseVerdict, string> = {
  SHIP: 'linear-gradient(135deg, var(--color-positive-weak) 0%, var(--color-bg) 100%)',
  HOLD: 'linear-gradient(135deg, var(--color-warning-weak) 0%, var(--color-bg) 100%)',
  ROLLBACK: 'linear-gradient(135deg, var(--color-negative-weak) 0%, var(--color-bg) 100%)',
}

const QUALITY_CLASS: Record<DataQualityStatus, string> = {
  healthy: 'chip-positive',
  warning: 'chip-warning',
  critical: 'chip-negative',
}

function formatSignedPct(value: number | null): string {
  if (value === null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}pp`
}

function EvaluateNowButton({ domain, projectId, experimentId }: { domain: string; projectId: string; experimentId: string }) {
  const { t } = useTranslation()
  const createEvaluation = useCreateReleaseEvaluation(domain, projectId)
  const [errorText, setErrorText] = useState<string | null>(null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
      <button
        type="button"
        className="btn btn-primary"
        disabled={createEvaluation.isPending}
        onClick={() => {
          setErrorText(null)
          createEvaluation.mutate(
            { experimentId },
            { onError: (err) => setErrorText(err instanceof ApiError ? err.detail : t('releaseDecision.evaluationFailed')) },
          )
        }}
      >
        {createEvaluation.isPending ? t('releaseDecision.evaluating') : t('releaseDecision.evaluateNow')}
      </button>
      {errorText && <span className="text-muted" style={{ fontSize: 11.5, maxWidth: 260, textAlign: 'right' }}>{errorText}</span>}
    </div>
  )
}

/** Decision-first release screen (Stage 14): the verdict and why it was
 * reached come before anything else — everything on this page is a
 * direct read of GET .../release-summary, never recomputed here.
 *
 * Stage 16 task 5: a PM reaches this page from the Experiment/Overview
 * nav (AppLayout's "Release Decision" link, already project/domain-aware)
 * with no URL to type, and "Evaluate now" runs a fresh release evaluation
 * in place -- previously the only way to populate this screen for an
 * experiment with no prior evaluation was to call the release-evaluations
 * POST endpoint directly, outside the UI entirely. */
export function ReleaseDecision() {
  const { t } = useTranslation()
  const { experimentId } = useParams<{ experimentId: string }>()
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const { data, isLoading, error } = useReleaseSummary(domain, projectId, experimentId)
  const { data: history } = useReleaseHistory(domain, projectId, experimentId)

  // Stage 17 task 10: a 404 here means "this experiment has no release
  // evaluation yet" -- an expected, common state (a brand-new experiment
  // has never had "Evaluate now" clicked), not a request failure. Without
  // this check it fell into the generic ErrorState branch below and
  // showed a raw "Not found" alert instead of the empty state's
  // "Evaluate now" button -- the one and only way to get out of that
  // state from this screen.
  const isNotYetEvaluated = error instanceof ApiError && error.status === 404

  if (isLoading) return <div className="page"><LoadingState label={t('releaseDecision.loading')} /></div>
  if (error && !isNotYetEvaluated) return <div className="page"><ErrorState error={error} /></div>
  if (!data) {
    return (
      <div className="page">
        <EmptyState>{t('releaseDecision.noEvaluationYet')}</EmptyState>
        {domain && projectId && experimentId && (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <EvaluateNowButton domain={domain} projectId={projectId} experimentId={experimentId} />
          </div>
        )}
      </div>
    )
  }

  const { decision, explanation_text, evidence_hierarchy, findings, representative_sessions, economics, data_quality_status, monitoring_window } = data

  return (
    <div className="page">
      {/* -- verdict, prominently -- */}
      <div className="page-hero" style={{ background: VERDICT_HERO_BG[decision.verdict] }}>
        {/* Stage 20: kept inside the hero's own bounds -- a rotated
            decoration positioned to straddle the border edge was
            observed escaping overflow:hidden clipping in Chromium. */}
        <div className="deco deco-bar" aria-hidden="true" style={{ width: 110, height: 20, top: 20, right: 14, background: 'var(--color-cyan)', opacity: 0.5 }} />
        <div className="page-hero-content" style={{ display: 'flex', alignItems: 'flex-end', gap: 20, justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
            <span className={`chip chip-verdict ${VERDICT_CLASS[decision.verdict]}`}>
              {decision.verdict}
            </span>
            <div>
              <h1 style={{ marginBottom: 4, fontSize: 26 }}>{explanation_text}</h1>
              <p className="text-secondary" style={{ margin: 0 }}>
                {decision.raw_verdict !== decision.verdict && (
                  <span>{t('releaseDecision.underlyingVerdict', { verdict: decision.raw_verdict })}</span>
                )}
                {t('releaseDecision.confidence', { confidence: decision.confidence.replace('_', ' ') })}
              </p>
            </div>
          </div>
          {domain && projectId && experimentId && <EvaluateNowButton domain={domain} projectId={projectId} experimentId={experimentId} />}
        </div>
      </div>

      {history && history.evaluations.length > 1 && (
        <div className="card">
          <div className="card-header">
            <h2>{t('releaseDecision.verdictHistory')}</h2>
            <p>{t('releaseDecision.verdictHistorySub')}</p>
          </div>
          <ReleaseTrendChart evaluations={history.evaluations} />
        </div>
      )}

      <div className="grid-3">
        {/* -- metric change -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            {t('releaseDecision.primaryMetric')}
          </div>
          <h3 style={{ marginBottom: 10 }}>{humanizeMetricName(decision.primary_metric)}</h3>
          <div style={{ display: 'flex', gap: 18 }}>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v1')}</div>
              <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{decision.primary_metric_v1 !== null ? `${(decision.primary_metric_v1 * 100).toFixed(1)}%` : '—'}</div>
            </div>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v2')}</div>
              <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{decision.primary_metric_v2 !== null ? `${(decision.primary_metric_v2 * 100).toFixed(1)}%` : '—'}</div>
            </div>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>{t('common.delta')}</div>
              <span className="chip chip-neutral">{formatSignedPct(decision.primary_metric_delta)}</span>
            </div>
          </div>
          <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>p = {formatPValue(decision.primary_metric_p_value)}</div>
        </div>

        {/* -- guardrails -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            {t('releaseDecision.guardrails')}
          </div>
          <h3 style={{ marginBottom: 10 }}>{decision.breached_guardrails.length > 0 ? t('releaseDecision.breachDetected') : t('releaseDecision.allWithinThreshold')}</h3>
          {decision.breached_guardrails.length === 0 && <p className="text-secondary" style={{ fontSize: 13 }}>{t('releaseDecision.noGuardrailBreached')}</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {decision.breached_guardrails.map((g) => (
              <div key={String(g.name)} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                <span>{String(g.name).replace(/_/g, ' ')}</span>
                <span className="chip chip-negative" style={{ fontSize: 10.5 }}>{String(g.severity ?? t('releaseDecision.breached'))}</span>
              </div>
            ))}
          </div>
        </div>

        {/* -- economics -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            {t('releaseDecision.economicsImpact')}
          </div>
          {economics === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>{t('releaseDecision.noEconomicsConfig')}</p>
          ) : decision.economics_impact === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>{t('releaseDecision.businessImpactUnavailable')}</p>
          ) : (
            <>
              <h3 style={{ marginBottom: 6 }}>{t('releaseDecision.perSession', { value: decision.economics_impact.toFixed(4) })}</h3>
              <span className={`chip ${decision.economics_impact >= 0 ? 'chip-positive' : 'chip-negative'}`}>
                {decision.economics_impact >= 0 ? t('releaseDecision.positiveImpact') : t('releaseDecision.negativeImpact')}
              </span>
            </>
          )}
        </div>
      </div>

      {/* -- data quality + monitoring window -- */}
      <div className="grid-3">
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            {t('releaseDecision.dataQuality')}
          </div>
          <span className={`chip ${QUALITY_CLASS[data_quality_status]}`}>{data_quality_status}</span>
          {decision.data_quality_gated && <p className="text-secondary" style={{ fontSize: 12.5, marginTop: 8 }}>{t('releaseDecision.shipWithheld')}</p>}
        </div>
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            {t('releaseDecision.monitoringWindow')}
          </div>
          {monitoring_window.window_hours === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>{t('releaseDecision.manualEvaluation')}</p>
          ) : (
            <>
              <h3 style={{ marginBottom: 4 }}>{t('releaseDecision.lastHours', { hours: monitoring_window.window_hours })}</h3>
              <p className="text-secondary" style={{ fontSize: 12 }}>
                {monitoring_window.data_window_start && formatDateTime(monitoring_window.data_window_start)} → {monitoring_window.data_window_end && formatDateTime(monitoring_window.data_window_end)}
              </p>
            </>
          )}
        </div>
      </div>

      {/* -- why this decision: evidence hierarchy -- */}
      <div className="card">
        <h2 style={{ marginBottom: 10 }}>{t('releaseDecision.whyThisDecision')}</h2>
        <ol style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 20 }}>
          {evidence_hierarchy.map((item) => (
            <li key={item.rank} style={{ fontSize: 13.5, lineHeight: 1.6 }}>
              {item.summary}
            </li>
          ))}
          {evidence_hierarchy.length === 0 && <p className="text-secondary">{t('releaseDecision.noEvidence')}</p>}
        </ol>
      </div>

      {/* -- top negative segments / findings -- */}
      {findings.length > 0 && (
        <div className="card">
          <h2 style={{ marginBottom: 10 }}>{t('releaseDecision.significantFindings')}</h2>
          {findings.length > 1 && (
            <div style={{ marginBottom: 16 }}>
              <SegmentEffectChart
                rows={findings.filter((f) => f.excess_contribution !== null).map((f) => ({ segment_label: f.segment_label, excess_contribution: f.excess_contribution as number }))}
              />
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {findings.map((f) => (
              <div key={f.segment_label} style={{ borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <strong>{humanizeSegmentLabel(f.segment_label)}</strong>
                  <span className="text-muted" style={{ fontSize: 11 }}>p = {formatPValue(f.p_value)}</span>
                </div>
                <p className="text-secondary" style={{ fontSize: 12.5, margin: '4px 0' }}>
                  {f.metric}: v1={f.v1_value !== null ? (f.v1_value * 100).toFixed(1) : '—'}% → v2={f.v2_value !== null ? (f.v2_value * 100).toFixed(1) : '—'}% ({formatSignedPct(f.delta)}), {t('releaseDecision.excessContribution', { value: f.excess_contribution?.toFixed(4) ?? '—' })}
                  {f.dominant_failure_mode && <> · {t('releaseDecision.mechanism', { value: f.dominant_failure_mode })}</>}
                </p>
                <p style={{ fontSize: 12.5 }}>{f.next_action}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* -- representative sessions -- */}
      {representative_sessions.length > 0 && (
        <div className="card">
          <h2 style={{ marginBottom: 10 }}>{t('releaseDecision.representativeSessions')}</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {representative_sessions.map((s) => (
              <div key={s.session_id} style={{ borderTop: '1px solid var(--color-border)', paddingTop: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <Link to={`/sessions/${s.session_id}`} className="mono">{s.session_id.slice(0, 8)}…</Link>
                  <span className={`chip ${s.human_review_status === 'reviewed' ? 'chip-positive' : 'chip-neutral'}`} style={{ fontSize: 10.5 }}>
                    {s.human_review_status.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-secondary" style={{ fontSize: 12, margin: '4px 0' }}>
                  {t('releaseDecision.outcomeSegment', { outcome: s.outcome, segment: humanizeSegmentLabel(s.segment_label) })}
                  {s.detected_mechanisms.length > 0 && <> · {t('releaseDecision.mechanisms', { value: s.detected_mechanisms.join(', ') })}</>}
                </p>
                <p className="text-muted" style={{ fontSize: 11.5, fontStyle: 'italic' }}>{s.selected_because}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
