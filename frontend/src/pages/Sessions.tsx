import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDomainMechanisms, useDomainSessions, useSegmentDimensions } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { formatDateTime } from '../lib/format'
import { useActiveExperiment } from '../state/ActiveExperimentContext'
import { useActiveProject } from '../state/ActiveProjectContext'

const PAGE_SIZE = 25
const KNOWN_PARAMS = new Set(['offset', 'experiment_id', 'agent_version', 'outcome', 'started_after', 'started_before', 'detected_mechanism', 'review_status'])

const OUTCOME_CHIP: Record<string, string> = {
  resolved: 'chip-positive',
  converted: 'chip-positive',
  purchase: 'chip-positive',
  abandoned: 'chip-negative',
  escalated: 'chip-negative',
}

const REVIEW_STATUS_CHIP: Record<string, string> = {
  unreviewed: 'chip-neutral',
  confirmed: 'chip-positive',
  rejected: 'chip-negative',
  mixed: 'chip-warning',
}

function toDayStart(date: string): string {
  return `${date}T00:00:00`
}
function toDayEnd(date: string): string {
  return `${date}T23:59:59`
}
function fromDayBoundary(value: string): string {
  return value.slice(0, 10)
}

/** Stage 16: domain-generic. Stage 17 task 3: restores useful filtering
 * without hardcoding any domain's vocabulary -- outcome and time range
 * are generic (every domain's sessions have some outcome + started_at),
 * detected-mechanism and review-status filters only render when this
 * domain actually has mechanisms (list_domain_mechanisms is the same
 * "empty is valid" signal used everywhere else), and configured context
 * dimensions come entirely from GET .../segment-dimensions -- this file
 * never lists a dimension or outcome value by name. */
export function Sessions() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { activeProject } = useActiveProject()
  const { activeExperimentId } = useActiveExperiment()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id

  const { data: mechanismsData } = useDomainMechanisms(domain, projectId)
  const { data: dimensionsData } = useSegmentDimensions(domain, projectId)
  const mechanisms = mechanismsData?.mechanisms ?? []
  const dimensions = dimensionsData?.dimensions ?? {}

  const offset = Number(searchParams.get('offset') ?? '0')
  const experimentId = searchParams.get('experiment_id') ?? activeExperimentId ?? undefined
  const agentVersion = searchParams.get('agent_version') ?? undefined
  const outcome = searchParams.get('outcome') ?? ''
  const startedAfter = searchParams.get('started_after') ?? ''
  const startedBefore = searchParams.get('started_before') ?? ''
  const detectedMechanism = searchParams.get('detected_mechanism') ?? ''
  const reviewStatus = searchParams.get('review_status') ?? ''

  const dimensionFilters: Record<string, string> = {}
  for (const key of Object.keys(dimensions)) {
    const value = searchParams.get(key)
    if (value) dimensionFilters[key] = value
  }
  // Any OTHER param not recognized above (e.g. a segment dimension this
  // project doesn't have loaded into `dimensions` yet, or one arriving
  // from a Finding's "View sessions" link) is still forwarded as-is --
  // the backend applies whichever of its own registered dimensions
  // match and ignores the rest, so this page never has to know every
  // dimension in advance to forward it correctly.
  const passthroughFilters: Record<string, string> = {}
  for (const [key, value] of searchParams.entries()) {
    if (!KNOWN_PARAMS.has(key) && !(key in dimensions) && !(key in dimensionFilters)) passthroughFilters[key] = value
  }

  const { data, isLoading, error } = useDomainSessions(domain, projectId, {
    experiment_id: experimentId,
    agent_version: agentVersion,
    outcome: outcome || undefined,
    started_after: startedAfter ? toDayStart(startedAfter) : undefined,
    started_before: startedBefore ? toDayEnd(startedBefore) : undefined,
    detected_mechanism: detectedMechanism || undefined,
    review_status: reviewStatus || undefined,
    limit: PAGE_SIZE,
    offset,
    ...dimensionFilters,
    ...passthroughFilters,
  })

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('offset')
    setSearchParams(next)
  }

  function clearFilters() {
    setSearchParams(activeExperimentId ? { experiment_id: activeExperimentId } : {})
  }

  function goToOffset(next: number) {
    const params = new URLSearchParams(searchParams)
    params.set('offset', String(next))
    setSearchParams(params)
  }

  const activeFilterEntries = Array.from(searchParams.entries()).filter(([k]) => k !== 'offset' && k !== 'experiment_id')
  const activeStructuredKeys = new Set(['agent_version', 'outcome', 'started_after', 'started_before', 'detected_mechanism', 'review_status', ...Object.keys(dimensions)])
  const activeExtraEntries = activeFilterEntries.filter(([k]) => !activeStructuredKeys.has(k))

  return (
    <div className="page">
      <div>
        <h1>{t('sessions.title')}</h1>
        <p className="text-secondary">{t('sessions.subtitle')}</p>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('sessions.filters')}</h2>
          {activeFilterEntries.length > 0 && (
            <button type="button" className="btn btn-small" onClick={clearFilters}>{t('sessions.clearAll', { count: activeFilterEntries.length })}</button>
          )}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('sessions.agentVersion')}</span>
            <select className="filter-input" value={agentVersion ?? ''} onChange={(e) => updateFilter('agent_version', e.target.value)}>
              <option value="">{t('sessions.any')}</option>
              <option value="v1">v1</option>
              <option value="v2">v2</option>
            </select>
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('sessions.outcome')}</span>
            <input
              type="text"
              className="filter-input"
              value={outcome}
              placeholder={t('sessions.any')}
              onChange={(e) => updateFilter('outcome', e.target.value)}
              style={{ width: 120 }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('sessions.startedAfter')}</span>
            <input type="date" className="filter-input" value={startedAfter ? fromDayBoundary(startedAfter) : ''} onChange={(e) => updateFilter('started_after', e.target.value)} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('sessions.startedBefore')}</span>
            <input type="date" className="filter-input" value={startedBefore ? fromDayBoundary(startedBefore) : ''} onChange={(e) => updateFilter('started_before', e.target.value)} />
          </label>

          {mechanisms.length > 0 && (
            <>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                <span className="text-muted">{t('sessions.detectedMechanism')}</span>
                <select className="filter-input" value={detectedMechanism} onChange={(e) => updateFilter('detected_mechanism', e.target.value)}>
                  <option value="">{t('sessions.any')}</option>
                  {mechanisms.map((m) => (
                    <option key={m.name} value={m.name}>{m.name.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                <span className="text-muted">{t('sessions.reviewStatus')}</span>
                <select className="filter-input" value={reviewStatus} onChange={(e) => updateFilter('review_status', e.target.value)}>
                  <option value="">{t('sessions.any')}</option>
                  <option value="unreviewed">{t('sessions.unreviewed')}</option>
                  <option value="confirmed">{t('sessions.confirmed')}</option>
                  <option value="rejected">{t('sessions.rejected')}</option>
                  <option value="mixed">{t('sessions.mixed')}</option>
                </select>
              </label>
            </>
          )}

          {Object.entries(dimensions).map(([dim, values]) => (
            <label key={dim} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              <span className="text-muted">{dim.replace(/_/g, ' ')}</span>
              <select className="filter-input" value={dimensionFilters[dim] ?? ''} onChange={(e) => updateFilter(dim, e.target.value)}>
                <option value="">Any</option>
                {values.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
          ))}

          {activeExtraEntries.map(([k, v]) => (
            <span key={k} className="chip chip-accent" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {k.replace(/_/g, ' ')}: {v}
              <button
                type="button"
                aria-label={t('sessions.removeFilter', { key: k })}
                onClick={() => updateFilter(k, '')}
                style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'inherit', fontWeight: 700, padding: 0, lineHeight: 1 }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        {isLoading && <LoadingState label={t('sessions.loadingSessions')} />}
        {error && <ErrorState error={error} />}
        {data && data.items.length === 0 && <EmptyState>{t('sessions.noSessionsMatch')}</EmptyState>}
        {data && data.items.length > 0 && (
          <>
            <p className="text-secondary" style={{ marginBottom: 12, fontSize: 12.5 }}>
              {t('sessions.sessionsMatch', { total: data.total.toLocaleString('en-US'), from: offset + 1, to: Math.min(offset + PAGE_SIZE, data.total) })}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('sessions.session')}</th>
                    <th>{t('sessions.version')}</th>
                    <th>{t('sessions.outcome')}</th>
                    {mechanisms.length > 0 && <th>{t('sessions.mechanisms')}</th>}
                    {mechanisms.length > 0 && <th>{t('sessions.review')}</th>}
                    <th>{t('sessions.started')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr
                      key={s.session_id}
                      className="clickable"
                      onClick={() => navigate(`/sessions/${s.session_id}`)}
                      role="button"
                      tabIndex={0}
                      aria-label={t('sessions.openSession', { id: s.session_id.slice(0, 8) })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          navigate(`/sessions/${s.session_id}`)
                        }
                      }}
                    >
                      <td className="mono">{s.session_id.slice(0, 8)}…</td>
                      <td>{s.agent_version}</td>
                      <td>{s.outcome ? <span className={`chip ${OUTCOME_CHIP[s.outcome] ?? 'chip-neutral'}`}>{s.outcome.replace(/_/g, ' ')}</span> : '—'}</td>
                      {mechanisms.length > 0 && (
                        <td className="text-secondary" style={{ fontSize: 11.5 }}>
                          {s.detected_mechanisms.length > 0 ? s.detected_mechanisms.map((m) => m.replace(/_/g, ' ')).join(', ') : '—'}
                        </td>
                      )}
                      {mechanisms.length > 0 && (
                        <td>
                          <span className={`chip ${REVIEW_STATUS_CHIP[s.review_status]}`} style={{ fontSize: 10.5 }}>{s.review_status}</span>
                        </td>
                      )}
                      <td className="text-muted">{s.started_at ? formatDateTime(s.started_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}>
                {t('sessions.previous')}
              </button>
              <button type="button" className="btn btn-small" disabled={offset + PAGE_SIZE >= data.total} onClick={() => goToOffset(offset + PAGE_SIZE)}>
                {t('sessions.next')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
