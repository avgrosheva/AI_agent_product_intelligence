import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useClassifierEvaluation, useDomainMechanisms, useGenericExperiments, useReviewQueue, useSubmitReview, type ReviewQueueFilters } from '../api/hooks'
import type { ReviewQueueItem } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { useActiveProject } from '../state/ActiveProjectContext'

const PAGE_SIZE = 25

function ReviewQueueRow({ item, domain, projectId, filters, mechanismNames }: {
  item: ReviewQueueItem
  domain: string
  projectId: string
  filters: ReviewQueueFilters
  mechanismNames: string[]
}) {
  const { t } = useTranslation()
  const [showCorrect, setShowCorrect] = useState(false)
  const [correctedMechanism, setCorrectedMechanism] = useState('')
  const [note, setNote] = useState('')
  const submit = useSubmitReview(domain, projectId, filters)
  const [errorText, setErrorText] = useState<string | null>(null)

  function submitDecision(decision: 'confirmed' | 'rejected', mechanism?: string) {
    setErrorText(null)
    submit.mutate(
      { sessionId: item.session_id, failureMode: item.failure_mode, decision, correctedMechanism: mechanism, note: note || undefined },
      {
        onError: (err) => setErrorText(err instanceof Error ? err.message : t('reviewQueue.reviewSubmissionFailed')),
        onSuccess: () => setShowCorrect(false),
      },
    )
  }

  return (
    <tr className={item.high_impact ? 'row-highlight' : undefined}>
      <td>
        <Link to={`/sessions/${item.session_id}`} className="mono">{item.session_id.slice(0, 8)}…</Link>
        <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
          {item.high_impact && <span className="chip chip-accent" style={{ fontSize: 10 }}>{t('reviewQueue.highImpact')}</span>}
          {item.is_newest_version && <span className="chip chip-warning" style={{ fontSize: 10 }} title={t('reviewQueue.newVersionTooltip')}>{t('reviewQueue.newVersion')}</span>}
        </div>
      </td>
      <td>{item.agent_version}</td>
      <td>{item.failure_mode.replace(/_/g, ' ')}</td>
      <td className="text-secondary" style={{ fontSize: 11.5 }}>
        {item.detector_source.replace(/_/g, ' ')}
        <div className="mono" style={{ fontSize: 10 }}>{item.detector_version}</div>
        {item.provider && <div style={{ fontSize: 10 }}>{item.provider}/{item.model}</div>}
      </td>
      <td className="mono">{item.confidence !== null ? `${(item.confidence * 100).toFixed(0)}%` : '—'}</td>
      <td style={{ maxWidth: 260, fontSize: 11.5 }} className="text-secondary">{item.evidence_text ?? '—'}</td>
      <td>
        {item.reviewed ? (
          <span className="chip chip-positive">{t('reviewQueue.reviewed')}</span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}>
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
                  {mechanismNames.filter((m) => m !== item.failure_mode).map((m) => (
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
        )}
      </td>
    </tr>
  )
}

/** Stage 18 task 2: a project-scoped view of backend.app.routers.review's
 * review queue (built Stage 6, never exposed in the UI until now) --
 * confirm/reject/correct a detector's attribution, with a note, and jump
 * straight to the session (and its evidence, already shown on
 * SessionDetail) the attribution came from. */
export function ReviewQueue() {
  const { t } = useTranslation()
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: experimentsData } = useGenericExperiments(domain, projectId)
  const { data: mechanismsData } = useDomainMechanisms(domain, projectId)
  const { data: classifierEval } = useClassifierEvaluation()

  const offset = Number(searchParams.get('offset') ?? '0')
  const experimentId = searchParams.get('experiment_id') ?? undefined
  const mechanism = searchParams.get('mechanism') ?? undefined
  const unreviewedOnly = searchParams.get('show_all') !== '1'

  const filters: ReviewQueueFilters = { experiment_id: experimentId, mechanism, unreviewed_only: unreviewedOnly, limit: PAGE_SIZE, offset }
  const { data, isLoading, error } = useReviewQueue(domain, projectId, filters)

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('offset')
    setSearchParams(next)
  }

  function goToOffset(next: number) {
    const params = new URLSearchParams(searchParams)
    params.set('offset', String(next))
    setSearchParams(params)
  }

  if (!activeProject || !domain || !projectId) {
    return <div className="page"><EmptyState>{t('reviewQueue.noProjectSelected')}</EmptyState></div>
  }

  const mechanismNames = (mechanismsData?.mechanisms ?? []).map((m) => m.name)

  return (
    <div className="page">
      <div>
        <h1>{t('reviewQueue.title')}</h1>
        <p className="text-secondary">{t('reviewQueue.subtitle')}</p>
      </div>

      {classifierEval && <MockClassifierBanner provenance={classifierEval.provenance} />}

      <div className="card">
        <div className="card-header"><h2>{t('reviewQueue.filters')}</h2></div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('reviewQueue.experiment')}</span>
            <select className="filter-input" value={experimentId ?? ''} onChange={(e) => updateFilter('experiment_id', e.target.value)} aria-label={t('reviewQueue.filterByExperiment')}>
              <option value="">{t('reviewQueue.any')}</option>
              {(experimentsData?.experiments ?? []).map((e) => (
                <option key={e.experiment_id} value={e.experiment_id}>{e.name}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('reviewQueue.mechanism')}</span>
            <select className="filter-input" value={mechanism ?? ''} onChange={(e) => updateFilter('mechanism', e.target.value)} aria-label={t('reviewQueue.filterByMechanism')}>
              <option value="">{t('reviewQueue.any')}</option>
              {mechanismNames.map((m) => (
                <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5 }}>
            <input type="checkbox" checked={!unreviewedOnly} onChange={(e) => updateFilter('show_all', e.target.checked ? '1' : '')} />
            {t('reviewQueue.showAlreadyReviewed')}
          </label>
        </div>
      </div>

      <div className="card">
        {isLoading && <LoadingState label={t('reviewQueue.loadingQueue')} />}
        {error && <ErrorState error={error} />}
        {data && data.items.length === 0 && <EmptyState>{t('reviewQueue.nothingToReview')}</EmptyState>}
        {data && data.items.length > 0 && (
          <>
            <p className="text-secondary" style={{ marginBottom: 12, fontSize: 12.5 }}>
              {t('reviewQueue.itemsMatch', { total: data.total.toLocaleString('en-US'), from: offset + 1, to: Math.min(offset + PAGE_SIZE, data.total) })}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('reviewQueue.session')}</th>
                    <th>{t('reviewQueue.version')}</th>
                    <th>{t('reviewQueue.mechanism')}</th>
                    <th>{t('reviewQueue.detector')}</th>
                    <th>{t('reviewQueue.confidence')}</th>
                    <th>{t('reviewQueue.evidence')}</th>
                    <th>{t('reviewQueue.decision')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <ReviewQueueRow
                      key={`${item.session_id}:${item.failure_mode}`}
                      item={item}
                      domain={domain}
                      projectId={projectId}
                      filters={filters}
                      mechanismNames={mechanismNames}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}>
                {t('reviewQueue.previous')}
              </button>
              <button type="button" className="btn btn-small" disabled={offset + PAGE_SIZE >= data.total} onClick={() => goToOffset(offset + PAGE_SIZE)}>
                {t('reviewQueue.next')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
