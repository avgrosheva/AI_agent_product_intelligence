import { useParams } from 'react-router-dom'
import { useClassifierEvaluation, useDomainAIQuality, useDomainMetrics } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import { formatPercent } from '../lib/format'
import { useActiveProject } from '../state/ActiveProjectContext'

/** Stage 16: domain-generic (previously called commerce-only,
 * project-unscoped endpoints). The classifier's evaluation provenance is
 * process-global, not per-domain/experiment, so it's read once from
 * useClassifierEvaluation (unchanged) rather than embedded per response.
 * offline_task_success_rate / constraint_satisfaction_rate are commerce
 * metric names with no support equivalent -- their cards simply don't
 * render for a domain that doesn't implement them, the same graceful
 * degradation this page already had before Stage 16. */
export function AIQuality() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const { data: quality, isLoading, error } = useDomainAIQuality(domain, projectId, experimentId)
  const { data: evaluation } = useClassifierEvaluation()
  const { data: metrics } = useDomainMetrics(domain, projectId, experimentId)

  if (isLoading) return <div className="page"><LoadingState label="Loading AI quality summary…" /></div>
  if (error) return <div className="page"><ErrorState error={error} /></div>
  if (!quality) return <div className="page"><EmptyState>No AI-quality data available.</EmptyState></div>

  const offlineSuccess = metrics?.metrics.find((m) => m.metric_name === 'offline_task_success_rate')
  const constraintSat = metrics?.metrics.find((m) => m.metric_name === 'constraint_satisfaction_rate')

  return (
    <div className="page">
      <div>
        <h1>AI Quality</h1>
        <p className="text-secondary">Model/agent behavior quality, independent of the business funnel.</p>
      </div>

      {evaluation && <MockClassifierBanner provenance={evaluation.provenance} />}

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
        {quality.failure_mechanism_prevalence.length === 0 ? (
          <EmptyState>This domain has no registered failure mechanisms.</EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Mechanism</th><th>Source</th><th>v1 rate</th><th>v1 count</th><th>v2 rate</th><th>v2 count</th><th>Reviewed</th></tr></thead>
              <tbody>
                {quality.failure_mechanism_prevalence.map((f) => (
                  <tr key={f.failure_mode}>
                    <td>{f.failure_mode.replace(/_/g, ' ')}</td>
                    <td className="text-muted">{f.detector_source.replace(/_/g, ' ')}</td>
                    <td className="mono">{formatPercent(f.rate_v1)}</td>
                    <td className="text-muted">{f.count_v1}</td>
                    <td className="mono">{formatPercent(f.rate_v2)}</td>
                    <td className="text-muted">{f.count_v2}</td>
                    <td className="text-muted">{f.reviewed_count > 0 ? `${f.confirmed_count}/${f.reviewed_count} confirmed` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header"><h2>Tool-use quality</h2></div>
        <div className="grid-3">
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool calls / session</div>
            <div style={{ fontSize: 14 }}>
              v1 {quality.tool_use_quality.tool_calls_per_session_v1?.toFixed(2) ?? '—'} · v2 {quality.tool_use_quality.tool_calls_per_session_v2?.toFixed(2) ?? '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool success rate</div>
            <div style={{ fontSize: 14 }}>
              v1 {formatPercent(quality.tool_use_quality.tool_success_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_success_rate_v2)}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>Tool error rate</div>
            <div style={{ fontSize: 14 }}>
              {quality.tool_use_quality.tool_error_rate_v1 === null
                ? 'Not tracked for this domain'
                : <>v1 {formatPercent(quality.tool_use_quality.tool_error_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_error_rate_v2)}</>}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>Trajectory summaries</h2><p>Descriptive frequency + outcome rate — not a statistically-tested Investigation finding.</p></div>
        {quality.trajectory_patterns.length === 0 && <EmptyState>No trajectory pattern met the minimum session count.</EmptyState>}
        {quality.trajectory_patterns.length > 0 && (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Pattern</th><th>n (v1)</th><th>n (v2)</th><th>negative outcome v1</th><th>negative outcome v2</th></tr></thead>
              <tbody>
                {quality.trajectory_patterns.slice(0, 10).map((t) => (
                  <tr key={t.pattern}>
                    <td className="mono" style={{ fontSize: 11.5 }}>{t.pattern}</td>
                    <td>{t.n_sessions_v1}</td>
                    <td>{t.n_sessions_v2}</td>
                    <td className="mono">{formatPercent(t.negative_outcome_rate_v1)}</td>
                    <td className="mono">{formatPercent(t.negative_outcome_rate_v2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {evaluation?.hybrid_evaluation && (
        <div className="card">
          <div className="card-header">
            <h2>Hybrid attribution evaluation (current)</h2>
            <p>
              Held-out benchmark of the CURRENT architecture — deterministic detectors + one semantic LLM call per
              session — against independent multi-label ground truth. See AI_EVALUATION.md §5.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16, fontSize: 12.5 }}>
            <div><span className="text-muted">Subset</span> <strong>{evaluation.hybrid_evaluation.subset}</strong> ({evaluation.hybrid_evaluation.subset_size} sessions, seed {evaluation.hybrid_evaluation.evaluation_seed})</div>
            <div><span className="text-muted">Provider / model</span> <strong>{evaluation.hybrid_evaluation.provider} / {evaluation.hybrid_evaluation.model}</strong></div>
            <div><span className="text-muted">Prompt / detector version</span> <strong>{evaluation.hybrid_evaluation.prompt_version} / {evaluation.hybrid_evaluation.detector_version}</strong></div>
            {evaluation.hybrid_evaluation.evaluated_at && <div><span className="text-muted">Evaluated</span> <strong>{new Date(evaluation.hybrid_evaluation.evaluated_at).toLocaleDateString()}</strong></div>}
          </div>

          <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>Deterministic detectors</h3>
          <p className="text-muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{evaluation.hybrid_evaluation.deterministic_detectors_note}</p>
          <div className="table-scroll" style={{ marginBottom: 20 }}>
            <table className="data-table">
              <thead><tr><th>Mechanism</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead>
              <tbody>
                {evaluation.hybrid_evaluation.deterministic_detectors.map((d) => (
                  <tr key={d.failure_mode}>
                    <td>{d.failure_mode.replace(/_/g, ' ')}</td>
                    <td className="mono">{formatPercent(d.precision)}</td>
                    <td className="mono">{formatPercent(d.recall)}</td>
                    <td className="mono">{formatPercent(d.f1)}</td>
                    <td className="text-muted">{d.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>Semantic call (one LLM request per session)</h3>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 10, fontSize: 12.5 }}>
            <div><span className="text-muted">Micro F1</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_micro_f1)}</strong></div>
            <div><span className="text-muted">Macro F1</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_macro_f1)}</strong></div>
            <div><span className="text-muted">Exact-match ratio</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_exact_match_ratio)}</strong></div>
            <div><span className="text-muted">Hamming loss</span> <strong>{evaluation.hybrid_evaluation.semantic_hamming_loss.toFixed(3)}</strong></div>
            <div><span className="text-muted">Response coverage</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_coverage)}</strong></div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Mechanism</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead>
              <tbody>
                {evaluation.hybrid_evaluation.semantic_metrics.map((s) => (
                  <tr key={s.failure_mode}>
                    <td>{s.failure_mode.replace(/_/g, ' ')}</td>
                    <td className="mono">{formatPercent(s.precision)}</td>
                    <td className="mono">{formatPercent(s.recall)}</td>
                    <td className="mono">{formatPercent(s.f1)}</td>
                    <td className="text-muted">{s.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {evaluation && evaluation.overall_accuracy !== null && (
        <div className="card">
          <div className="card-header">
            <h2>Classifier evaluation (legacy exclusive-classifier shape)</h2>
            <p>Deprecated architecture — kept only for historical comparison. See "Hybrid attribution evaluation" above for the current pipeline.</p>
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
              <div className="table-scroll">
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
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
