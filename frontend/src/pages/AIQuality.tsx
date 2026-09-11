import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useClassifierEvaluation, useDomainAIQuality, useDomainMetrics } from '../api/hooks'
import type { QualityCounts } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { MetricComparisonRow } from '../components/common/MetricComparisonRow'
import { formatDateShort, formatPercent } from '../lib/format'
import { useActiveProject } from '../state/ActiveProjectContext'

/** Stage 19 task 3: renders "insufficient_review_data" as a visible
 * caveat right next to the rate it qualifies, never as a separate,
 * easy-to-miss banner -- a confirmation rate from 2 reviews should never
 * be read with the same confidence as one from 50. */
function RateWithSampleWarning({ rate, counts }: { rate: number | null; counts: QualityCounts }) {
  const { t } = useTranslation()
  return (
    <span>
      <span className="mono">{rate === null ? '—' : formatPercent(rate)}</span>
      <span className="text-muted" style={{ fontSize: 10.5, marginLeft: 4 }}>
        (n={counts.reviewed_count})
      </span>
      {counts.sample_status === 'insufficient_review_data' && (
        <span className="chip chip-warning" style={{ fontSize: 9.5, marginLeft: 4, padding: '1px 5px' }} title={t('aiQuality.lowSampleTooltip')}>
          {t('aiQuality.lowSample')}
        </span>
      )}
    </span>
  )
}

/** Stage 16: domain-generic (previously called commerce-only,
 * project-unscoped endpoints). The classifier's evaluation provenance is
 * process-global, not per-domain/experiment, so it's read once from
 * useClassifierEvaluation (unchanged) rather than embedded per response.
 * offline_task_success_rate / constraint_satisfaction_rate are commerce
 * metric names with no support equivalent -- their cards simply don't
 * render for a domain that doesn't implement them, the same graceful
 * degradation this page already had before Stage 16. */
export function AIQuality() {
  const { t } = useTranslation()
  const { experimentId } = useParams<{ experimentId: string }>()
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const { data: quality, isLoading, error } = useDomainAIQuality(domain, projectId, experimentId)
  const { data: evaluation } = useClassifierEvaluation()
  const { data: metrics } = useDomainMetrics(domain, projectId, experimentId)

  if (isLoading) return <div className="page"><LoadingState label={t('aiQuality.loading')} /></div>
  if (error) return <div className="page"><ErrorState error={error} /></div>
  if (!quality) return <div className="page"><EmptyState>{t('aiQuality.noData')}</EmptyState></div>

  const offlineSuccess = metrics?.metrics.find((m) => m.metric_name === 'offline_task_success_rate')
  const constraintSat = metrics?.metrics.find((m) => m.metric_name === 'constraint_satisfaction_rate')

  return (
    <div className="page">
      <div>
        <h1>{t('aiQuality.title')}</h1>
        <p className="text-secondary">{t('aiQuality.subtitle')}</p>
      </div>

      {evaluation && <MockClassifierBanner provenance={evaluation.provenance} />}

      <div className="grid-2">
        {offlineSuccess && (
          <div className="card">
            <h2 style={{ marginBottom: 10 }}>{t('aiQuality.offlineTaskSuccess')}</h2>
            <MetricComparisonRow metric={offlineSuccess} showName={false} />
          </div>
        )}
        {constraintSat && (
          <div className="card">
            <h2 style={{ marginBottom: 10 }}>{t('aiQuality.constraintSatisfaction')}</h2>
            <MetricComparisonRow metric={constraintSat} showName={false} />
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header"><h2>{t('aiQuality.failureMechanismPrevalence')}</h2><p>{t('aiQuality.failureMechanismPrevalenceSub')}</p></div>
        {quality.failure_mechanism_prevalence.length === 0 ? (
          <EmptyState>{t('aiQuality.noRegisteredMechanisms')}</EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>{t('aiQuality.mechanism')}</th><th>{t('aiQuality.source')}</th><th>{t('aiQuality.v1Rate')}</th><th>{t('aiQuality.v1Count')}</th><th>{t('aiQuality.v2Rate')}</th><th>{t('aiQuality.v2Count')}</th><th>{t('aiQuality.reviewed')}</th></tr></thead>
              <tbody>
                {quality.failure_mechanism_prevalence.map((f) => (
                  <tr key={f.failure_mode}>
                    <td>{f.failure_mode.replace(/_/g, ' ')}</td>
                    <td className="text-muted">{f.detector_source.replace(/_/g, ' ')}</td>
                    <td className="mono">{formatPercent(f.rate_v1)}</td>
                    <td className="text-muted">{f.count_v1}</td>
                    <td className="mono">{formatPercent(f.rate_v2)}</td>
                    <td className="text-muted">{f.count_v2}</td>
                    <td className="text-muted">{f.reviewed_count > 0 ? t('aiQuality.confirmedOf', { confirmed: f.confirmed_count, reviewed: f.reviewed_count }) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('aiQuality.humanReviewQuality')}</h2>
          <p>
            {t('aiQuality.humanReviewQualitySub')}
          </p>
        </div>
        {quality.human_review_quality.overall.reviewed_count === 0 ? (
          <EmptyState>{t('aiQuality.noAttributionsReviewed')}</EmptyState>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 18 }}>
              <div>
                <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.confirmationRate')}</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>
                  <RateWithSampleWarning rate={quality.human_review_quality.overall.confirmation_rate} counts={quality.human_review_quality.overall} />
                </div>
              </div>
              <div>
                <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.correctionRate')}</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>
                  <RateWithSampleWarning rate={quality.human_review_quality.overall.correction_rate} counts={quality.human_review_quality.overall} />
                </div>
              </div>
              <div>
                <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.confirmedRejectedCorrected')}</div>
                <div style={{ fontSize: 14 }}>
                  {quality.human_review_quality.overall.confirmed_count} / {quality.human_review_quality.overall.rejected_count} / {quality.human_review_quality.overall.corrected_count}
                </div>
              </div>
            </div>

            <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.qualityByMechanism')}</h3>
            <div className="table-scroll" style={{ marginBottom: 20 }}>
              <table className="data-table">
                <thead><tr><th>{t('aiQuality.mechanism')}</th><th>{t('aiQuality.source')}</th><th>{t('aiQuality.confirmationRate')}</th><th>{t('aiQuality.correctionRate')}</th></tr></thead>
                <tbody>
                  {quality.human_review_quality.by_mechanism.map((m) => (
                    <tr key={m.failure_mode}>
                      <td>{m.failure_mode.replace(/_/g, ' ')}</td>
                      <td className="text-muted">{m.detector_source.replace(/_/g, ' ')}</td>
                      <td><RateWithSampleWarning rate={m.counts.confirmation_rate} counts={m.counts} /></td>
                      <td><RateWithSampleWarning rate={m.counts.correction_rate} counts={m.counts} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.deterministicVsLlm')}</h3>
            <div className="table-scroll" style={{ marginBottom: 20 }}>
              <table className="data-table">
                <thead><tr><th>{t('aiQuality.detectorSource')}</th><th>{t('aiQuality.confirmationRate')}</th><th>{t('aiQuality.correctionRate')}</th></tr></thead>
                <tbody>
                  {quality.human_review_quality.by_detector_source.map((s) => (
                    <tr key={s.detector_source}>
                      <td>{s.detector_source.replace(/_/g, ' ')}</td>
                      <td><RateWithSampleWarning rate={s.counts.confirmation_rate} counts={s.counts} /></td>
                      <td><RateWithSampleWarning rate={s.counts.correction_rate} counts={s.counts} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.confidenceBucketHeading')}</h3>
            <p className="text-muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t('aiQuality.confidenceBucketSub')}</p>
            <div className="table-scroll" style={{ marginBottom: 20 }}>
              <table className="data-table">
                <thead><tr><th>{t('aiQuality.confidenceBucket')}</th><th>{t('aiQuality.confirmationRate')}</th></tr></thead>
                <tbody>
                  {quality.human_review_quality.by_confidence_bucket.map((b) => (
                    <tr key={b.bucket_label}>
                      <td className="mono">{b.bucket_label}</td>
                      <td><RateWithSampleWarning rate={b.counts.confirmation_rate} counts={b.counts} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.qualityOverTime')}</h3>
            <p className="text-muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t('aiQuality.qualityOverTimeSub')}</p>
            <div className="table-scroll" style={{ marginBottom: 20 }}>
              <table className="data-table">
                <thead><tr><th>{t('aiQuality.detectorVersion')}</th><th>{t('aiQuality.providerModelPrompt')}</th><th>{t('aiQuality.firstSeen')}</th><th>{t('aiQuality.confirmationRate')}</th></tr></thead>
                <tbody>
                  {quality.human_review_quality.by_version.map((v) => (
                    <tr key={`${v.detector_version}:${v.provider}:${v.model}:${v.prompt_version}`}>
                      <td className="mono">{v.detector_version}</td>
                      <td className="text-secondary" style={{ fontSize: 11.5 }}>{v.provider ? `${v.provider} / ${v.model} / ${v.prompt_version}` : '—'}</td>
                      <td className="text-muted">{formatDateShort(v.first_seen)}</td>
                      <td><RateWithSampleWarning rate={v.counts.confirmation_rate} counts={v.counts} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.mostCommonCorrections')}</h3>
            {quality.human_review_quality.confusion_pairs.length === 0 ? (
              <EmptyState>{t('aiQuality.noCorrectedYet')}</EmptyState>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>{t('aiQuality.detectedAs')}</th><th>{t('aiQuality.actuallyWas')}</th><th>{t('aiQuality.count')}</th></tr></thead>
                  <tbody>
                    {quality.human_review_quality.confusion_pairs.map((p) => (
                      <tr key={`${p.original_mechanism}:${p.corrected_mechanism}`}>
                        <td>{p.original_mechanism.replace(/_/g, ' ')}</td>
                        <td>{p.corrected_mechanism.replace(/_/g, ' ')}</td>
                        <td className="mono">{p.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header"><h2>{t('aiQuality.toolUseQuality')}</h2></div>
        <div className="grid-3">
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.toolCallsPerSession')}</div>
            <div style={{ fontSize: 14 }}>
              v1 {quality.tool_use_quality.tool_calls_per_session_v1?.toFixed(2) ?? '—'} · v2 {quality.tool_use_quality.tool_calls_per_session_v2?.toFixed(2) ?? '—'}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.toolSuccessRate')}</div>
            <div style={{ fontSize: 14 }}>
              v1 {formatPercent(quality.tool_use_quality.tool_success_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_success_rate_v2)}
            </div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.toolErrorRate')}</div>
            <div style={{ fontSize: 14 }}>
              {quality.tool_use_quality.tool_error_rate_v1 === null
                ? t('aiQuality.notTrackedForDomain')
                : <>v1 {formatPercent(quality.tool_use_quality.tool_error_rate_v1)} · v2 {formatPercent(quality.tool_use_quality.tool_error_rate_v2)}</>}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h2>{t('aiQuality.trajectorySummaries')}</h2><p>{t('aiQuality.trajectorySummariesSub')}</p></div>
        {quality.trajectory_patterns.length === 0 && <EmptyState>{t('aiQuality.noTrajectoryPattern')}</EmptyState>}
        {quality.trajectory_patterns.length > 0 && (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>{t('aiQuality.pattern')}</th><th>{t('aiQuality.nV1')}</th><th>{t('aiQuality.nV2')}</th><th>{t('aiQuality.negativeOutcomeV1')}</th><th>{t('aiQuality.negativeOutcomeV2')}</th></tr></thead>
              <tbody>
                {quality.trajectory_patterns.slice(0, 10).map((t2) => (
                  <tr key={t2.pattern}>
                    <td className="mono" style={{ fontSize: 11.5 }}>{t2.pattern}</td>
                    <td>{t2.n_sessions_v1}</td>
                    <td>{t2.n_sessions_v2}</td>
                    <td className="mono">{formatPercent(t2.negative_outcome_rate_v1)}</td>
                    <td className="mono">{formatPercent(t2.negative_outcome_rate_v2)}</td>
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
            <h2>{t('aiQuality.hybridEvaluation')}</h2>
            <p>
              {t('aiQuality.hybridEvaluationSub')}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16, fontSize: 12.5 }}>
            <div><span className="text-muted">{t('aiQuality.subset')}</span> <strong>{evaluation.hybrid_evaluation.subset}</strong> {t('aiQuality.subsetDetail', { size: evaluation.hybrid_evaluation.subset_size, seed: evaluation.hybrid_evaluation.evaluation_seed })}</div>
            <div><span className="text-muted">{t('aiQuality.providerModel')}</span> <strong>{evaluation.hybrid_evaluation.provider} / {evaluation.hybrid_evaluation.model}</strong></div>
            <div><span className="text-muted">{t('aiQuality.promptDetectorVersion')}</span> <strong>{evaluation.hybrid_evaluation.prompt_version} / {evaluation.hybrid_evaluation.detector_version}</strong></div>
            {evaluation.hybrid_evaluation.evaluated_at && <div><span className="text-muted">{t('aiQuality.evaluated')}</span> <strong>{new Date(evaluation.hybrid_evaluation.evaluated_at).toLocaleDateString()}</strong></div>}
          </div>

          <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.deterministicDetectors')}</h3>
          <p className="text-muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{evaluation.hybrid_evaluation.deterministic_detectors_note}</p>
          <div className="table-scroll" style={{ marginBottom: 20 }}>
            <table className="data-table">
              <thead><tr><th>{t('aiQuality.mechanism')}</th><th>{t('aiQuality.precision')}</th><th>{t('aiQuality.recall')}</th><th>{t('aiQuality.f1')}</th><th>{t('aiQuality.support')}</th></tr></thead>
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

          <h3 style={{ marginBottom: 8, fontSize: 13.5 }}>{t('aiQuality.semanticCall')}</h3>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 10, fontSize: 12.5 }}>
            <div><span className="text-muted">{t('aiQuality.microF1')}</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_micro_f1)}</strong></div>
            <div><span className="text-muted">{t('aiQuality.macroF1')}</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_macro_f1)}</strong></div>
            <div><span className="text-muted">{t('aiQuality.exactMatchRatio')}</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_exact_match_ratio)}</strong></div>
            <div><span className="text-muted">{t('aiQuality.hammingLoss')}</span> <strong>{evaluation.hybrid_evaluation.semantic_hamming_loss.toFixed(3)}</strong></div>
            <div><span className="text-muted">{t('aiQuality.responseCoverage')}</span> <strong>{formatPercent(evaluation.hybrid_evaluation.semantic_coverage)}</strong></div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>{t('aiQuality.mechanism')}</th><th>{t('aiQuality.precision')}</th><th>{t('aiQuality.recall')}</th><th>{t('aiQuality.f1')}</th><th>{t('aiQuality.support')}</th></tr></thead>
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
            <h2>{t('aiQuality.legacyClassifierEvaluation')}</h2>
            <p>{t('aiQuality.legacyClassifierEvaluationSub')}</p>
          </div>
          {evaluation.overall_accuracy === null ? (
            <EmptyState>{t('aiQuality.noEvaluationRun')}</EmptyState>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 24, marginBottom: 14 }}>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.overallAccuracy')}</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{formatPercent(evaluation.overall_accuracy)}</div>
                </div>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.sessionsEvaluated')}</div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{evaluation.n_sessions_evaluated?.toLocaleString('en-US')}</div>
                </div>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>{t('aiQuality.acceptanceBars')}</div>
                  <span className={`chip ${evaluation.all_acceptance_bars_met ? 'chip-positive' : 'chip-negative'}`}>
                    {evaluation.all_acceptance_bars_met ? t('aiQuality.allMet') : t('aiQuality.notAllMet')}
                  </span>
                </div>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>{t('aiQuality.failureMode')}</th><th>{t('aiQuality.recall')}</th><th>{t('aiQuality.bar')}</th><th>{t('aiQuality.precision')}</th><th>{t('aiQuality.bar')}</th></tr></thead>
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
