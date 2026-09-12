import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcknowledgeAlert, useAlerts, useGenericExperiments, type AlertFilters } from '../api/hooks'
import type { Alert, AlertSeverity, AlertStatus } from '../api/types'
import { ApiError } from '../api/client'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { formatDateTime, humanizeMetricName } from '../lib/format'
import { useActiveProject } from '../state/ActiveProjectContext'

const PAGE_SIZE = 25

const RULE_LABEL_KEY: Record<string, string> = {
  rollback: 'alerts.ruleRollback',
  blocking_guardrail_breach: 'alerts.ruleBlockingGuardrail',
  hold_negative_segment: 'alerts.ruleHoldNegativeSegment',
}

function AlertRow({ alert, projectId, filters }: { alert: Alert; projectId: string; filters: AlertFilters }) {
  const { t } = useTranslation()
  const acknowledge = useAcknowledgeAlert(projectId, filters)
  const [errorText, setErrorText] = useState<string | null>(null)

  return (
    <tr>
      <td className="text-secondary" style={{ fontSize: 12 }}>{formatDateTime(alert.created_at)}</td>
      <td><span className={`chip ${alert.severity === 'critical' ? 'chip-negative' : 'chip-warning'}`}>{alert.severity}</span></td>
      <td>{RULE_LABEL_KEY[alert.rule] ? t(RULE_LABEL_KEY[alert.rule]) : humanizeMetricName(alert.rule)}</td>
      <td style={{ maxWidth: 320, fontSize: 12.5 }}>{alert.reason}</td>
      <td className="text-secondary" style={{ fontSize: 11.5 }}>
        <div className="mono">{alert.experiment_id.slice(0, 8)}…</div>
        {alert.related_guardrail && <div>{t('alerts.guardrail', { value: humanizeMetricName(alert.related_guardrail) })}</div>}
        {alert.related_finding && <div>{t('alerts.finding', { value: alert.related_finding })}</div>}
      </td>
      <td>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
          <span className={`chip ${alert.status === 'open' ? 'chip-warning' : 'chip-positive'}`}>{alert.status}</span>
          {alert.acknowledged_at && <div className="text-muted" style={{ fontSize: 10.5 }}>{formatDateTime(alert.acknowledged_at)}</div>}
          {alert.status === 'open' && (
            <button
              type="button"
              className="btn btn-small"
              disabled={acknowledge.isPending}
              onClick={() => {
                setErrorText(null)
                acknowledge.mutate(alert.alert_id, {
                  onError: (err) => setErrorText(err instanceof ApiError ? err.detail : t('alerts.acknowledgeFailed')),
                })
              }}
            >
              {acknowledge.isPending ? t('alerts.acknowledging') : t('alerts.acknowledge')}
            </button>
          )}
          {errorText && <span className="chip chip-negative" style={{ fontSize: 10.5 }}>{errorText}</span>}
        </div>
      </td>
    </tr>
  )
}

/** Stage 18 task 1: a project-scoped view of backend.app.routers.alerts
 * (already built in Stage 6, never exposed in the UI until now) --
 * alerts fire as a deterministic side effect of a release evaluation
 * (backend.alerts.service.generate_alerts_for_evaluation), never
 * user-authored, so this screen is read + acknowledge only, no create
 * form. */
export function Alerts() {
  const { t } = useTranslation()
  const { activeProject } = useActiveProject()
  const projectId = activeProject?.project_id
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: experimentsData } = useGenericExperiments(activeProject?.domain, projectId)

  const offset = Number(searchParams.get('offset') ?? '0')
  const status = (searchParams.get('status') as AlertStatus | null) ?? undefined
  const severity = (searchParams.get('severity') as AlertSeverity | null) ?? undefined
  const experimentId = searchParams.get('experiment_id') ?? undefined

  const filters: AlertFilters = { status, severity, experiment_id: experimentId, limit: PAGE_SIZE, offset }
  const { data, isLoading, error } = useAlerts(projectId, filters)

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

  if (!activeProject || !projectId) {
    return <div className="page"><EmptyState>{t('alerts.noProjectSelected')}</EmptyState></div>
  }

  return (
    <div className="page">
      <div>
        <h1>{t('alerts.title')}</h1>
        <p className="text-secondary">{t('alerts.subtitle')}</p>
      </div>

      <div className="card">
        <div className="card-header"><h2>{t('alerts.filters')}</h2></div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('alerts.status')}</span>
            <select className="filter-input" value={status ?? ''} onChange={(e) => updateFilter('status', e.target.value)} aria-label={t('alerts.filterByStatus')}>
              <option value="">{t('alerts.any')}</option>
              <option value="open">{t('alerts.open')}</option>
              <option value="acknowledged">{t('alerts.acknowledged')}</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('alerts.severity')}</span>
            <select className="filter-input" value={severity ?? ''} onChange={(e) => updateFilter('severity', e.target.value)} aria-label={t('alerts.filterBySeverity')}>
              <option value="">{t('alerts.any')}</option>
              <option value="critical">{t('alerts.critical')}</option>
              <option value="warning">{t('alerts.warning')}</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <span className="text-muted">{t('alerts.experiment')}</span>
            <select className="filter-input" value={experimentId ?? ''} onChange={(e) => updateFilter('experiment_id', e.target.value)} aria-label={t('alerts.filterByExperiment')}>
              <option value="">{t('alerts.any')}</option>
              {(experimentsData?.experiments ?? []).map((e) => (
                <option key={e.experiment_id} value={e.experiment_id}>{e.name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="card">
        {isLoading && <LoadingState label={t('alerts.loadingAlerts')} />}
        {error && <ErrorState error={error} />}
        {data && data.alerts.length === 0 && <EmptyState>{t('alerts.noAlertsMatch')}</EmptyState>}
        {data && data.alerts.length > 0 && (
          <>
            <p className="text-secondary" style={{ marginBottom: 12, fontSize: 12.5 }}>
              {t('alerts.alertsMatch', { total: data.total.toLocaleString('en-US'), from: offset + 1, to: Math.min(offset + PAGE_SIZE, data.total) })}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('alerts.created')}</th>
                    <th>{t('alerts.severity')}</th>
                    <th>{t('alerts.rule')}</th>
                    <th>{t('alerts.reason')}</th>
                    <th>{t('alerts.context')}</th>
                    <th>{t('alerts.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.alerts.map((a) => (
                    <AlertRow key={a.alert_id} alert={a} projectId={projectId} filters={filters} />
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}>
                {t('alerts.previous')}
              </button>
              <button type="button" className="btn btn-small" disabled={offset + PAGE_SIZE >= data.total} onClick={() => goToOffset(offset + PAGE_SIZE)}>
                {t('alerts.next')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
