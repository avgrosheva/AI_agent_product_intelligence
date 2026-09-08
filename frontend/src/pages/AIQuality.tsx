import { useParams } from 'react-router-dom'
import { useAIQuality, useClassifierEvaluation, useExperimentMetrics } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import { formatPercent } from '../lib/format'

export function AIQuality() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const { data: quality, isLoading, error } = useAIQuality(experimentId)
  const { data: evaluation } = useClassifierEvaluation()
  const { data: metrics } = useExperimentMetrics(experimentId)

  if (isLoading) return <div className="page"><LoadingState label="Loading AI quality summary…" /></div>
  if (error) return <div className="page"><ErrorState message={(error as Error).message} /></div>
  if (!quality) return <div className="page"><EmptyState>No AI-quality data available.</EmptyState></div>

  const offlineSuccess = metrics?.metrics.find((m) => m.metric_name === 'offline_task_success_rate')
  const constraintSat = metrics?.metrics.find((m) => m.metric_name === 'constraint_satisfaction_rate')

  return (
    <div className="page">
      <div>
        <h1>AI Quality</h1>
        <p className="text-secondary">Model/agent behavior quality, independent of the business funnel.</p>
      </div>

      <MockClassifierBanner provenance={quality.classifier_provenance} />

      <div className="grid-2">
        {offlineSuccess && (
          <div className="card">
            <h2 style={{ marginBottom: 10 }}>Offline task success</h2>
            <MetricComparisonRow metric={offlineSuccess} showName={false} />
          </div>
        )}
        {constraintSat && (
          <div className="card">
            <h2 style={{ marginBottom: 10 }}>Constraint satisfaction</h2>
            <MetricComparisonRow metric={constraintSat} showName={false} />
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header"><h2>Failure mechanism prevalence</h2><p>Share of sessions where each mechanism's detector fired — mechanisms can overlap, so rates do not sum to 100%.</p></div>
        <table className="data-table">
          <thead><tr><th>Mechanism</th><th>Source</th><th>v1 rate</th><th>v1 count</th><th>v2 rate</th><th>v2 count</th></tr></thead>
          <tbody>
            {quality.failure_mechanism_prevalence.map((f) => (
              <tr key={f.failure_mode}>
                <td>{f.failure_mode.replace(/_/g, ' ')}</td>
                <td className="text-muted">{f.detector_source.replace(/_/g, ' ')}</td>
                <td className="mono">{formatPercent(f.rate_v1)}</td>
                <td className="text-muted">{f.count_v1}</td>
                <td className="mono">{formatPercent(f.rate_v2)}</td>
                <td className="text-muted">{f.count_v2}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-header"><h2>Tool-use quality</h2></div>
        <div className="grid-3">
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool calls / session</div>
            <div style={{ fontSize: 14 }}>v1 {quality.tool_use_quality.tool_calls_per_session_v1.toFixed(2)} · v2 {quality.tool_use_quality.tool_calls_per_session_v2.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool success rate</div>
            <div style={{ fontSize: 14 }}>v1 {formatPercent(quality.tool_use_quality.tool_success_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_success_rate_v2)}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool error rate</div>
            <div style={{ fontSize: 14 }}>v1 {formatPercent(quality.tool_use_quality.tool_error_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_error_rate_v2)}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>Trajectory summaries</h2><p>Descriptive frequency + outcome rate — not a statistically-tested Investigation finding.</p></div>
        {quality.trajectory_patterns.length === 0 && <EmptyState>No trajectory pattern met the minimum session count.</EmptyState>}
        {quality.trajectory_patterns.length > 0 && (
          <table className="data-table">
            <thead><tr><th>Pattern</th><th>n (v1)</th><th>n (v2)</th><th>abandonment v1</th><th>abandonment v2</th></tr></thead>
            <tbody>
              {quality.trajectory_patterns.slice(0, 10).map((t) => (
                <tr key={t.pattern}>
                  <td className="mono" style={{ fontSize: 11.5 }}>{t.pattern}</td>
                  <td>{t.n_sessions_v1}</td>
                  <td>{t.n_sessions_v2}</td>
                  <td className="mono">{formatPercent(t.abandonment_rate_v1)}</td>
                  <td className="mono">{formatPercent(t.abandonment_rate_v2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {evaluation && (
        <div className="card">
          <div className="card-header">
            <h2>Classifier evaluation</h2>
            <p>Offline evaluation against held-out ground truth (never used by the live classification/investigation pipeline).</p>
          </div>
          {evaluation.overall_accuracy === null ? (
            <EmptyState>No evaluation run recorded yet.</EmptyState>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 24, marginBottom: 14 }}>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Overall accuracy</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{formatPercent(evaluation.overall_accuracy)}</div>
                </div>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Sessions evaluated</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{evaluation.n_sessions_evaluated?.toLocaleString('en-US')}</div>
                </div>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Acceptance bars</div>
                  <span className={`chip ${evaluation.all_acceptance_bars_met ? 'chip-positive' : 'chip-negative'}`}>
                    {evaluation.all_acceptance_bars_met ? 'all met' : 'not all met'}
                  </span>
                </div>
              </div>
              <table className="data-table">
                <thead><tr><th>Failure mode</th><th>Recall</th><th>Bar</th><th>Precision</th><th>Bar</th></tr></thead>
                <tbody>
                  {evaluation.acceptance_bars.map((b) => (
                    <tr key={b.failure_mode}>
                      <td>{b.failure_mode.replace(/_/g, ' ')}</td>
                      <td className="mono">{formatPercent(b.recall)}</td>
                      <td><span className={`chip ${b.recall_pass ? 'chip-positive' : 'chip-negative'}`}>{'≥'}{formatPercent(b.recall_bar, 0)}</span></td>
                      <td className="mono">{formatPercent(b.precision)}</td>
                      <td><span className={`chip ${b.precision_pass ? 'chip-positive' : 'chip-negative'}`}>{'≥'}{formatPercent(b.precision_bar, 0)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}
