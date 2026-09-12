import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useClassifierEvaluation, useDomainMechanisms, useDomainSessionDetail, useSubmitSessionReview } from '../api/hooks'
import type { GenericFailureAttribution } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { formatDateTime } from '../lib/format'
import { useActiveProject } from '../state/ActiveProjectContext'

const OUTCOME_CHIP: Record<string, string> = {
  resolved: 'chip-positive',
  converted: 'chip-positive',
  purchase: 'chip-positive',
  abandoned: 'chip-negative',
  escalated: 'chip-negative',
}

/** Stage 21: the confirm/reject/correct controls the Review Queue table
 * offers, reachable from right where the evidence (transcript, tool
 * calls) that a reviewer actually needs to decide is already shown --
 * without this, reading that evidence here meant losing the review
 * controls and going back to the queue to act on what was just read. */
function ReviewActions({ domain, projectId, sessionId, attribution, mechanismNames }: {
  domain: string
  projectId: string
  sessionId: string
  attribution: GenericFailureAttribution
  mechanismNames: string[]
}) {
  const { t } = useTranslation()
  const [showCorrect, setShowCorrect] = useState(false)
  const [correctedMechanism, setCorrectedMechanism] = useState('')
  const [note, setNote] = useState('')
  const [errorText, setErrorText] = useState<string | null>(null)
  const submit = useSubmitSessionReview(domain, projectId, sessionId)

  function submitDecision(decision: 'confirmed' | 'rejected', mechanism?: string) {
    setErrorText(null)
    submit.mutate(
      { failureMode: attribution.failure_mode, decision, correctedMechanism: mechanism, note: note || undefined },
      {
        onError: (err) => setErrorText(err instanceof Error ? err.message : t('reviewQueue.reviewSubmissionFailed')),
        onSuccess: () => setShowCorrect(false),
      },
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start', marginTop: 6 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-small" disabled={submit.isPending} onClick={() => submitDecision('confirmed')}>
          {t('reviewQueue.confirm')}
        </button>
        <button type="button" className="btn btn-small" disabled={submit.isPending} onClick={() => submitDecision('rejected')}>
          {t('reviewQueue.reject')}
        </button>
        <button type="button" className="btn btn-small" disabled={submit.isPending} onClick={() => setShowCorrect((v) => !v)} aria-expanded={showCorrect}>
          {showCorrect ? t('reviewQueue.cancel') : t('reviewQueue.correctEllipsis')}
        </button>
      </div>
      {showCorrect && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            className="filter-input"
            value={correctedMechanism}
            onChange={(e) => setCorrectedMechanism(e.target.value)}
            aria-label={t('reviewQueue.correctedMechanism')}
          >
            <option value="">{t('reviewQueue.selectCorrectMechanism')}</option>
            {mechanismNames.filter((m) => m !== attribution.failure_mode).map((m) => (
              <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <input
            type="text"
            className="filter-input"
            placeholder={t('reviewQueue.noteOptional')}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ width: 160 }}
            aria-label={t('reviewQueue.reviewNote')}
          />
          <button
            type="button"
            className="btn btn-small btn-primary"
            disabled={submit.isPending || !correctedMechanism}
            onClick={() => submitDecision('rejected', correctedMechanism)}
          >
            {t('reviewQueue.submitCorrection')}
          </button>
        </div>
      )}
      {errorText && <span className="chip chip-negative" style={{ fontSize: 10.5 }}>{errorText}</span>}
    </div>
  )
}

/** Stage 16: domain-generic (previously called the legacy, unscoped
 * /sessions/{id} endpoint). The old commerce-only session detail carried
 * rich per-session fields (requested_category, platform, cost, token
 * counts, product recommendations, product events, per-message latency)
 * with no generic equivalent -- the generic ingestion schema only
 * guarantees a transcript, an action sequence, tool calls, and an
 * outcome. This screen shows exactly that, plus failure attributions;
 * "Show raw / technical detail" still exposes the full JSON response for
 * anything domain-specific ingested beyond the generic shape. */
export function SessionDetail() {
  const { t } = useTranslation()
  const { sessionId } = useParams<{ sessionId: string }>()
  const [showRaw, setShowRaw] = useState(false)
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const { data: session, isLoading, error } = useDomainSessionDetail(domain, projectId, sessionId)
  const { data: classifierEval } = useClassifierEvaluation()
  const { data: mechanismsData } = useDomainMechanisms(domain, projectId)
  const mechanismNames = (mechanismsData?.mechanisms ?? []).map((m) => m.name)

  if (isLoading) return <div className="page"><LoadingState label={t('sessionDetail.loadingSession')} /></div>
  if (error) return <div className="page"><ErrorState error={error} /></div>
  if (!session) return <div className="page"><EmptyState>{t('sessionDetail.notFound')}</EmptyState></div>

  return (
    <div className="page">
      <div>
        <Link to="/sessions" className="text-secondary" style={{ fontSize: 12.5 }}>{t('sessionDetail.backToSessions')}</Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
          <h1>{t('sessionDetail.session', { id: session.session_id.slice(0, 8) })}</h1>
          <span className={`chip ${OUTCOME_CHIP[session.outcome] ?? 'chip-neutral'}`}>{session.outcome.replace(/_/g, ' ')}</span>
          <span className="chip chip-neutral">{session.domain}</span>
        </div>
      </div>

      {session.failure_attributions.length > 0 && (
        <>
          {classifierEval && <MockClassifierBanner provenance={classifierEval.provenance} />}
          <div className="card">
            <div className="card-header"><h2>{t('sessionDetail.detectedMechanisms')}</h2><p>{t('sessionDetail.detectedMechanismsSub')}</p></div>
            {session.failure_attributions.map((f) => (
              <div key={f.failure_mode} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 4, flexWrap: 'wrap' }}>
                  <span className="chip chip-warning">{f.failure_mode.replace(/_/g, ' ')}</span>
                  <span className="text-muted" style={{ fontSize: 12 }}>{t('sessionDetail.source', { value: f.detector_source.replace(/_/g, ' ') })}</span>
                  {f.confidence !== null && (
                    <span className="text-muted" style={{ fontSize: 12 }}>{t('sessionDetail.confidence', { value: (f.confidence * 100).toFixed(0) })}</span>
                  )}
                  {f.review_status !== 'unreviewed' && (
                    <span className={`chip ${f.review_status === 'confirmed' ? 'chip-positive' : 'chip-negative'}`} style={{ fontSize: 10.5 }}>
                      {f.review_status}
                    </span>
                  )}
                </div>
                {/* Stage 19 task 8: version-level provenance -- always
                    visible (which detector version and, for semantic
                    mechanisms, which model/prompt actually produced
                    this), plus who reviewed it and when once it has
                    been. */}
                <div className="text-muted" style={{ fontSize: 10.5, marginBottom: 4 }}>
                  {t('sessionDetail.detector', { version: f.detector_version || '—' })}
                  {f.provider && ` · ${f.provider}/${f.model}`}
                  {f.prompt_version && ` · prompt ${f.prompt_version}`}
                  {f.review_status !== 'unreviewed' && (
                    <> · {t('sessionDetail.reviewed')}{f.reviewer ? t('sessionDetail.reviewedBy', { reviewer: f.reviewer }) : ''}{f.reviewed_at ? t('sessionDetail.reviewedOn', { date: formatDateTime(f.reviewed_at) }) : ''}</>
                  )}
                  {f.corrected_mechanism && t('sessionDetail.correctedTo', { value: f.corrected_mechanism.replace(/_/g, ' ') })}
                </div>
                {f.evidence_text && <p style={{ fontSize: 13 }}>{f.evidence_text}</p>}
                {f.review_status === 'unreviewed' && domain && projectId && sessionId && (
                  <ReviewActions domain={domain} projectId={projectId} sessionId={sessionId} attribution={f} mechanismNames={mechanismNames} />
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <div className="card">
        <div className="card-header">
          <h2>{t('sessionDetail.timeline')}</h2>
          <p>{t('sessionDetail.timelineSub')}</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {session.transcript.map(([sender, text], i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
              <span className="chip chip-neutral" style={{ minWidth: 56, textAlign: 'center', flexShrink: 0 }}>{sender}</span>
              <span style={{ fontSize: 13 }}>{text}</span>
            </div>
          ))}
          {session.transcript.length === 0 && <EmptyState>{t('sessionDetail.noTranscript')}</EmptyState>}
        </div>

        {session.action_sequence.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              {t('sessionDetail.actionSequence')}
            </div>
            <div className="mono" style={{ fontSize: 12.5 }}>{session.action_sequence.join(' → ')}</div>
          </div>
        )}

        {session.tool_calls.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              {t('sessionDetail.toolCalls')}
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>{t('sessionDetail.tool')}</th><th>{t('sessionDetail.success')}</th><th>{t('sessionDetail.error')}</th></tr></thead>
                <tbody>
                  {session.tool_calls.map((tc, i) => (
                    <tr key={i}>
                      <td>{tc.tool_name}</td>
                      <td>{tc.success ? t('sessionDetail.yes') : t('sessionDetail.no')}</td>
                      <td className="text-muted">{tc.error_type === 'none' ? '—' : tc.error_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <button type="button" className="btn btn-small" onClick={() => setShowRaw((v) => !v)} aria-expanded={showRaw}>
          {showRaw ? t('sessionDetail.hideRaw') : t('sessionDetail.showRaw')}
        </button>
        {showRaw && (
          <pre
            className="mono"
            style={{
              marginTop: 12, fontSize: 11, whiteSpace: 'pre-wrap', overflowX: 'auto',
              background: 'var(--color-surface-tint)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)', padding: 12,
            }}
          >
{JSON.stringify(session, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
