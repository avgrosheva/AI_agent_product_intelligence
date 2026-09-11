import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  useDataQuality,
  useGenericExperiments,
  useMonitoringConfigs,
  useNotificationChannels,
  useOnboardingStatus,
  useProjectConfig,
  useReleaseStatus,
} from '../api/hooks'
import type { GenericExperimentSummary } from '../api/types'
import { ErrorState } from '../components/common/States'
import { useActiveProject } from '../state/ActiveProjectContext'
import { categorizeStatus } from './onboarding/StatusPanel'

/** Stage 17 task 4: every card on this page reads a different query, so
 * "loading" and "request failed" have to be distinguished per card, not
 * once for the whole page -- one failed request (e.g. a 403 on a
 * project this user's role can't see monitoring for) must never render
 * as a silent, permanent "Loading…" the way it did before. */
function CardStatus({ isLoading, error, children }: { isLoading: boolean; error: unknown; children: ReactNode }) {
  if (error) return <ErrorState error={error} />
  if (isLoading) return <span className="text-muted">Loading…</span>
  return <>{children}</>
}

function ExperimentReleaseRow({ domain, projectId, experiment }: { domain: string; projectId: string; experiment: GenericExperimentSummary }) {
  const { data, isLoading, error } = useReleaseStatus(domain, projectId, experiment.experiment_id)
  return (
    <tr>
      <td>{experiment.name}</td>
      <td>
        {error ? (
          <span className="chip chip-negative" title={error instanceof Error ? error.message : String(error)}>error</span>
        ) : isLoading ? (
          <span className="text-muted">loading…</span>
        ) : data ? (
          <span className={`chip ${data.status === 'ROLLBACK' ? 'chip-negative' : data.status === 'HOLD' ? 'chip-warning' : 'chip-positive'}`}>{data.status}</span>
        ) : (
          <span className="chip chip-neutral">Not yet evaluated</span>
        )}
      </td>
      <td className="text-secondary" style={{ fontSize: 12.5 }}>{data?.primary_reason ?? '—'}</td>
    </tr>
  )
}

/** Stage 15 task 8: a single at-a-glance view of a project's health --
 * every field here is a read of an existing endpoint (onboarding-status,
 * data-quality, release-status, monitoring configs, notification
 * channels); nothing new is computed here. */
export function ProjectOverview() {
  const { activeProject, activeProjectId } = useActiveProject()
  const domain = activeProject?.domain
  const hasProject = !!activeProjectId && !!domain

  const statusQuery = useOnboardingStatus(domain, activeProjectId ?? undefined)
  const qualityQuery = useDataQuality(domain, activeProjectId ?? undefined)
  const configQuery = useProjectConfig(domain, activeProjectId ?? undefined)
  const experimentsQuery = useGenericExperiments(domain, activeProjectId ?? undefined)
  const monitoringQuery = useMonitoringConfigs(domain, activeProjectId ?? undefined)
  const channelsQuery = useNotificationChannels(domain, activeProjectId ?? undefined)

  if (!hasProject) {
    return (
      <div className="page">
        <h1>Project overview</h1>
        <div className="state-box">
          No project selected yet. <Link to="/setup">Go to project setup</Link> to select or create one.
        </div>
      </div>
    )
  }

  const groups = statusQuery.data ? categorizeStatus(statusQuery.data) : null

  return (
    <div className="page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <h1>{activeProject?.name}</h1>
          <p className="text-secondary">{activeProject?.domain} project</p>
        </div>
        <Link to="/setup" className="btn">Edit setup</Link>
      </div>

      <div className="grid-3">
        <div className="card">
          <div className="card-header"><h2>Readiness</h2></div>
          <CardStatus isLoading={statusQuery.isLoading} error={statusQuery.error}>
            {groups && (
              groups.blocking.length > 0 ? (
                <span className="chip chip-negative">{groups.blocking.length} blocking issue(s)</span>
              ) : (
                <span className="chip chip-positive">Ready for analysis</span>
              )
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>Data quality</h2></div>
          <CardStatus isLoading={qualityQuery.isLoading} error={qualityQuery.error}>
            {qualityQuery.data && (
              <span className={`chip ${qualityQuery.data.status === 'critical' ? 'chip-negative' : qualityQuery.data.status === 'warning' ? 'chip-warning' : 'chip-positive'}`}>
                {qualityQuery.data.status}
              </span>
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>Connector status</h2></div>
          <CardStatus isLoading={statusQuery.isLoading} error={statusQuery.error}>
            {statusQuery.data && (
              <span className={`chip ${statusQuery.data.ingestion_connected ? 'chip-positive' : 'chip-negative'}`}>
                {statusQuery.data.ingestion_connected ? 'Connected' : 'Not connected'}
              </span>
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>Monitoring</h2></div>
          <CardStatus isLoading={monitoringQuery.isLoading} error={monitoringQuery.error}>
            {(() => {
              const enabledMonitoringCount = (monitoringQuery.data?.configs ?? []).filter((c) => c.enabled).length
              return (
                <span className={`chip ${enabledMonitoringCount > 0 ? 'chip-positive' : 'chip-neutral'}`}>
                  {enabledMonitoringCount > 0 ? `${enabledMonitoringCount} active schedule(s)` : 'Not scheduled'}
                </span>
              )
            })()}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>Notifications</h2></div>
          <CardStatus isLoading={channelsQuery.isLoading || configQuery.isLoading} error={channelsQuery.error ?? configQuery.error}>
            {(() => {
              const enabledChannelCount = (channelsQuery.data?.channels ?? []).filter((c) => c.enabled).length
              return (
                <span className={`chip ${enabledChannelCount > 0 && (configQuery.data?.enabled_notification_rules.length ?? 0) > 0 ? 'chip-positive' : 'chip-neutral'}`}>
                  {enabledChannelCount} channel(s), {configQuery.data?.enabled_notification_rules.length ?? 0} event type(s)
                </span>
              )
            })()}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>Primary metric</h2></div>
          <CardStatus isLoading={configQuery.isLoading} error={configQuery.error}>
            <span className="mono">{configQuery.data?.primary_metric ?? 'not set'}</span>
          </CardStatus>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Latest release status</h2>
          <p>Per experiment in this project.</p>
        </div>
        {experimentsQuery.error ? (
          <ErrorState error={experimentsQuery.error} />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Experiment</th><th>Status</th><th>Reason</th></tr></thead>
              <tbody>
                {(experimentsQuery.data?.experiments ?? []).map((exp) => (
                  <ExperimentReleaseRow key={exp.experiment_id} domain={domain!} projectId={activeProjectId!} experiment={exp} />
                ))}
                {experimentsQuery.isLoading && (
                  <tr><td colSpan={3} className="text-muted">Loading…</td></tr>
                )}
                {!experimentsQuery.isLoading && (experimentsQuery.data?.experiments ?? []).length === 0 && (
                  <tr><td colSpan={3} className="text-muted">No experiments in this project yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
