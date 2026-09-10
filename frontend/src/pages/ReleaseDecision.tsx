import { Link, useParams } from 'react-router-dom'
import { useReleaseSummary } from '../api/hooks'
import type { DataQualityStatus, ReleaseVerdict } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { formatDateTime, formatPValue, humanizeMetricName, humanizeSegmentLabel } from '../lib/format'

const VERDICT_CLASS: Record<ReleaseVerdict, string> = {
  SHIP: 'chip-positive',
  HOLD: 'chip-warning',
  ROLLBACK: 'chip-negative',
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

/** Decision-first release screen (Stage 14): the verdict and why it was
 * reached come before anything else — everything on this page is a
 * direct read of GET .../release-summary, never recomputed here. */
export function ReleaseDecision() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const { data, isLoading, error } = useReleaseSummary(experimentId)

  if (isLoading) return <div className="page"><LoadingState label="Loading release decision…" /></div>
  if (error) return <div className="page"><ErrorState message={(error as Error).message} /></div>
  if (!data) return <div className="page"><EmptyState>No release evaluation has been run yet for this experiment.</EmptyState></div>

  const { decision, explanation_text, evidence_hierarchy, findings, representative_sessions, economics, data_quality_status, monitoring_window } = data

  return (
    <div className="page">
      {/* -- verdict, prominently -- */}
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span className={`chip ${VERDICT_CLASS[decision.verdict]}`} style={{ fontSize: 20, padding: '10px 20px' }}>
          {decision.verdict}
        </span>
        <div>
          <h1 style={{ marginBottom: 2 }}>{explanation_text}</h1>
          <p className="text-secondary" style={{ margin: 0 }}>
            {decision.raw_verdict !== decision.verdict && (
              <span>Underlying verdict: {decision.raw_verdict} (withheld due to data quality) · </span>
            )}
            Confidence: {decision.confidence.replace('_', ' ')}
          </p>
        </div>
      </div>

      <div className="grid-3">
        {/* -- metric change -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Primary metric
          </div>
          <h3 style={{ marginBottom: 10 }}>{humanizeMetricName(decision.primary_metric)}</h3>
          <div style={{ display: 'flex', gap: 18 }}>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>v1</div>
              <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{decision.primary_metric_v1 !== null ? `${(decision.primary_metric_v1 * 100).toFixed(1)}%` : '—'}</div>
            </div>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>v2</div>
              <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{decision.primary_metric_v2 !== null ? `${(decision.primary_metric_v2 * 100).toFixed(1)}%` : '—'}</div>
            </div>
            <div>
              <div className="text-muted" style={{ fontSize: 11 }}>delta</div>
              <span className="chip chip-neutral">{formatSignedPct(decision.primary_metric_delta)}</span>
            </div>
          </div>
          <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>p = {formatPValue(decision.primary_metric_p_value)}</div>
        </div>

        {/* -- guardrails -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Guardrails
          </div>
          <h3 style={{ marginBottom: 10 }}>{decision.breached_guardrails.length > 0 ? 'Breach detected' : 'All within threshold'}</h3>
          {decision.breached_guardrails.length === 0 && <p className="text-secondary" style={{ fontSize: 13 }}>No guardrail is currently breached.</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {decision.breached_guardrails.map((g) => (
              <div key={String(g.name)} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                <span>{String(g.name).replace(/_/g, ' ')}</span>
                <span className="chip chip-negative" style={{ fontSize: 10.5 }}>{String(g.severity ?? 'breached')}</span>
              </div>
            ))}
          </div>
        </div>

        {/* -- economics -- */}
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Economics impact
          </div>
          {economics === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>This domain has no economics configuration.</p>
          ) : decision.economics_impact === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>Business impact is unavailable (revenue/value data not ingested).</p>
          ) : (
            <>
              <h3 style={{ marginBottom: 6 }}>{decision.economics_impact.toFixed(4)} per session</h3>
              <span className={`chip ${decision.economics_impact >= 0 ? 'chip-positive' : 'chip-negative'}`}>
                {decision.economics_impact >= 0 ? 'Positive' : 'Negative'} impact
              </span>
            </>
          )}
        </div>
      </div>

      {/* -- data quality + monitoring window -- */}
      <div className="grid-3">
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Data quality
          </div>
          <span className={`chip ${QUALITY_CLASS[data_quality_status]}`}>{data_quality_status}</span>
          {decision.data_quality_gated && <p className="text-secondary" style={{ fontSize: 12.5, marginTop: 8 }}>A SHIP verdict was withheld because project data quality is critical.</p>}
        </div>
        <div className="card">
          <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Monitoring window
          </div>
          {monitoring_window.window_hours === null ? (
            <p className="text-secondary" style={{ fontSize: 13 }}>Manual evaluation — full history, no time window.</p>
          ) : (
            <>
              <h3 style={{ marginBottom: 4 }}>Last {monitoring_window.window_hours}h</h3>
              <p className="text-secondary" style={{ fontSize: 12 }}>
                {monitoring_window.data_window_start && formatDateTime(monitoring_window.data_window_start)} → {monitoring_window.data_window_end && formatDateTime(monitoring_window.data_window_end)}
              </p>
            </>
          )}
        </div>
      </div>

      {/* -- why this decision: evidence hierarchy -- */}
      <div className="card">
        <h2 style={{ marginBottom: 10 }}>Why this decision?</h2>
        <ol style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 20 }}>
          {evidence_hierarchy.map((item) => (
            <li key={item.rank} style={{ fontSize: 13.5, lineHeight: 1.6 }}>
              {item.summary}
            </li>
          ))}
          {evidence_hierarchy.length === 0 && <p className="text-secondary">No notable evidence beyond the primary metric itself.</p>}
        </ol>
      </div>

      {/* -- top negative segments / findings -- */}
      {findings.length > 0 && (
        <div className="card">
          <h2 style={{ marginBottom: 10 }}>Significant findings</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {findings.map((f) => (
              <div key={f.segment_label} style={{ borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <strong>{humanizeSegmentLabel(f.segment_label)}</strong>
                  <span className="text-muted" style={{ fontSize: 11 }}>p = {formatPValue(f.p_value)}</span>
                </div>
                <p className="text-secondary" style={{ fontSize: 12.5, margin: '4px 0' }}>
                  {f.metric}: v1={f.v1_value !== null ? (f.v1_value * 100).toFixed(1) : '—'}% → v2={f.v2_value !== null ? (f.v2_value * 100).toFixed(1) : '—'}% ({formatSignedPct(f.delta)}), excess contribution {f.excess_contribution?.toFixed(4) ?? '—'}
                  {f.dominant_failure_mode && <> · mechanism: {f.dominant_failure_mode}</>}
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
          <h2 style={{ marginBottom: 10 }}>Representative sessions</h2>
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
                  Outcome: {s.outcome} · Segment: {humanizeSegmentLabel(s.segment_label)}
                  {s.detected_mechanisms.length > 0 && <> · Mechanisms: {s.detected_mechanisms.join(', ')}</>}
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
