import { useNavigate, useSearchParams } from 'react-router-dom'
import { useSessions, type SessionFilters } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { DIMENSION_VALUES, FILTERABLE_DIMENSIONS } from '../lib/dimensionValues'
import { formatDateTime } from '../lib/format'
import { useActiveExperiment } from '../state/ActiveExperimentContext'

const PAGE_SIZE = 25

const OUTCOME_CHIP: Record<string, string> = {
  purchase: 'chip-positive',
  add_to_cart_only: 'chip-neutral',
  no_action: 'chip-neutral',
  abandoned: 'chip-negative',
}

export function Sessions() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { activeExperimentId } = useActiveExperiment()

  const offset = Number(searchParams.get('offset') ?? '0')
  const filters: SessionFilters = {
    experiment_id: searchParams.get('experiment_id') ?? activeExperimentId ?? undefined,
    agent_version: searchParams.get('agent_version') ?? undefined,
    requested_category: searchParams.get('requested_category') ?? undefined,
    constraint_count_bucket: searchParams.get('constraint_count_bucket') ?? undefined,
    platform: searchParams.get('platform') ?? undefined,
    device_tier: searchParams.get('device_tier') ?? undefined,
    locale: searchParams.get('locale') ?? undefined,
    persona: searchParams.get('persona') ?? undefined,
    outcome: searchParams.get('outcome') ?? undefined,
    failure_mode: searchParams.get('failure_mode') ?? undefined,
    limit: PAGE_SIZE,
    offset,
  }

  const { data, isLoading, error } = useSessions(filters)

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

  const activeFilterCount = FILTERABLE_DIMENSIONS.filter((d) => searchParams.get(d.key)).length

  return (
    <div className="page">
      <div>
        <h1>Sessions</h1>
        <p className="text-secondary">Drill from a statistical finding into concrete session examples.</p>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Filters</h2>
          {activeFilterCount > 0 && (
            <button type="button" className="btn btn-small" onClick={clearFilters}>Clear all ({activeFilterCount})</button>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {FILTERABLE_DIMENSIONS.map((dim) => (
            <label key={dim.key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              <span className="text-muted">{dim.label}</span>
              <select
                value={searchParams.get(dim.key) ?? ''}
                onChange={(e) => updateFilter(dim.key, e.target.value)}
                style={{ padding: '6px 8px', borderRadius: 4, border: '1px solid var(--color-border-strong)' }}
              >
                <option value="">Any</option>
                {DIMENSION_VALUES[dim.key]?.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </div>

      <div className="card">
        {isLoading && <LoadingState label="Loading sessions…" />}
        {error && <ErrorState message={(error as Error).message} />}
        {data && data.items.length === 0 && <EmptyState>No sessions match these filters.</EmptyState>}
        {data && data.items.length > 0 && (
          <>
            <p className="text-secondary" style={{ marginBottom: 12, fontSize: 12.5 }}>
              {data.total.toLocaleString('en-US')} sessions match · showing {offset + 1}-{Math.min(offset + PAGE_SIZE, data.total)}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Session</th>
                    <th>Version</th>
                    <th>Request</th>
                    <th>Platform</th>
                    <th>Outcome</th>
                    <th>Failure mode</th>
                    <th>Latency</th>
                    <th>Cost</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr key={s.session_id} className="clickable" onClick={() => navigate(`/sessions/${s.session_id}`)}>
                      <td className="mono">{s.session_id.slice(0, 8)}…</td>
                      <td>{s.agent_version}</td>
                      <td>{s.requested_category}, {s.constraint_count_bucket} constraints</td>
                      <td>{s.platform}</td>
                      <td><span className={`chip ${OUTCOME_CHIP[s.outcome] ?? 'chip-neutral'}`}>{s.outcome.replace(/_/g, ' ')}</span></td>
                      <td>{s.detected_failure_modes.length > 0 ? s.detected_failure_modes.join(', ') : '—'}</td>
                      <td className="mono">{s.total_latency_ms.toLocaleString('en-US')}ms</td>
                      <td className="mono">${s.total_cost_usd.toFixed(4)}</td>
                      <td className="text-muted">{formatDateTime(s.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}>
                ← Previous
              </button>
              <button type="button" className="btn btn-small" disabled={offset + PAGE_SIZE >= data.total} onClick={() => goToOffset(offset + PAGE_SIZE)}>
                Next →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
