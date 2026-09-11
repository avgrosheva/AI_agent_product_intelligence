import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  if (error) return <ErrorState error={error} />
  if (isLoading) return <span className="text-muted">{t('common.loading')}</span>
  return <>{children}</>
}

function ExperimentReleaseRow({ domain, projectId, experiment }: { domain: string; projectId: string; experiment: GenericExperimentSummary }) {
  const { t } = useTranslation()
  const { data, isLoading, error } = useReleaseStatus(domain, projectId, experiment.experiment_id)
  return (
    <tr>
      <td>{experiment.name}</td>
      <td>
        {error ? (
          <span className="chip chip-negative" title={error instanceof Error ? error.message : String(error)}>{t('projectOverview.error')}</span>
        ) : isLoading ? (
          <span className="text-muted">{t('common.loading')}</span>
        ) : data ? (
          <span className={`chip ${data.status === 'ROLLBACK' ? 'chip-negative' : data.status === 'HOLD' ? 'chip-warning' : 'chip-positive'}`}>{data.status}</span>
        ) : (
          <span className="chip chip-neutral">{t('projectOverview.notYetEvaluated')}</span>
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
  const { t } = useTranslation()
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
        <h1>{t('projectOverview.title')}</h1>
        <div className="state-box">
          {t('projectOverview.noProjectSelected')} <Link to="/setup">{t('projectOverview.goToSetup')}</Link>{t('projectOverview.toSelectOrCreate')}
        </div>
      </div>
    )
  }

  const groups = statusQuery.data ? categorizeStatus(statusQuery.data) : null

  return (
    <div className="page">
      <div className="page-hero">
        <div className="deco deco-pixels" aria-hidden="true" style={{ width: 130, height: 130, top: -30, right: 60, color: 'var(--color-cyan)' }} />
        <div className="page-hero-content" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1>{activeProject?.name}</h1>
            <p className="text-secondary">{t('projectOverview.domainProject', { domain: activeProject?.domain })}</p>
          </div>
          <Link to="/setup" className="btn">{t('projectOverview.editSetup')}</Link>
        </div>
      </div>

      <div className="grid-3">
        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.readiness')}</h2></div>
          <CardStatus isLoading={statusQuery.isLoading} error={statusQuery.error}>
            {groups && (
              groups.blocking.length > 0 ? (
                <span className="chip chip-negative">{t('projectOverview.blockingIssues', { count: groups.blocking.length })}</span>
              ) : (
                <span className="chip chip-positive">{t('projectOverview.readyForAnalysis')}</span>
              )
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.dataQuality')}</h2></div>
          <CardStatus isLoading={qualityQuery.isLoading} error={qualityQuery.error}>
            {qualityQuery.data && (
              <span className={`chip ${qualityQuery.data.status === 'critical' ? 'chip-negative' : qualityQuery.data.status === 'warning' ? 'chip-warning' : 'chip-positive'}`}>
                {qualityQuery.data.status}
              </span>
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.connectorStatus')}</h2></div>
          <CardStatus isLoading={statusQuery.isLoading} error={statusQuery.error}>
            {statusQuery.data && (
              <span className={`chip ${statusQuery.data.ingestion_connected ? 'chip-positive' : 'chip-negative'}`}>
                {statusQuery.data.ingestion_connected ? t('projectOverview.connected') : t('projectOverview.notConnected')}
              </span>
            )}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.monitoring')}</h2></div>
          <CardStatus isLoading={monitoringQuery.isLoading} error={monitoringQuery.error}>
            {(() => {
              const enabledMonitoringCount = (monitoringQuery.data?.configs ?? []).filter((c) => c.enabled).length
              return (
                <span className={`chip ${enabledMonitoringCount > 0 ? 'chip-positive' : 'chip-neutral'}`}>
                  {enabledMonitoringCount > 0 ? t('projectOverview.activeSchedules', { count: enabledMonitoringCount }) : t('projectOverview.notScheduled')}
                </span>
              )
            })()}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.notifications')}</h2></div>
          <CardStatus isLoading={channelsQuery.isLoading || configQuery.isLoading} error={channelsQuery.error ?? configQuery.error}>
            {(() => {
              const enabledChannelCount = (channelsQuery.data?.channels ?? []).filter((c) => c.enabled).length
              return (
                <span className={`chip ${enabledChannelCount > 0 && (configQuery.data?.enabled_notification_rules.length ?? 0) > 0 ? 'chip-positive' : 'chip-neutral'}`}>
                  {t('projectOverview.channelsAndEvents', { channels: enabledChannelCount, events: configQuery.data?.enabled_notification_rules.length ?? 0 })}
                </span>
              )
            })()}
          </CardStatus>
        </div>

        <div className="card">
          <div className="card-header"><h2>{t('projectOverview.primaryMetric')}</h2></div>
          <CardStatus isLoading={configQuery.isLoading} error={configQuery.error}>
            <span className="mono">{configQuery.data?.primary_metric ?? t('projectOverview.notSet')}</span>
          </CardStatus>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('projectOverview.latestReleaseStatus')}</h2>
          <p>{t('projectOverview.perExperiment')}</p>
        </div>
        {experimentsQuery.error ? (
          <ErrorState error={experimentsQuery.error} />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>{t('projectOverview.experiment')}</th><th>{t('projectOverview.status')}</th><th>{t('projectOverview.reason')}</th></tr></thead>
              <tbody>
                {(experimentsQuery.data?.experiments ?? []).map((exp) => (
                  <ExperimentReleaseRow key={exp.experiment_id} domain={domain!} projectId={activeProjectId!} experiment={exp} />
                ))}
                {experimentsQuery.isLoading && (
                  <tr><td colSpan={3} className="text-muted">{t('common.loading')}</td></tr>
                )}
                {!experimentsQuery.isLoading && (experimentsQuery.data?.experiments ?? []).length === 0 && (
                  <tr><td colSpan={3} className="text-muted">{t('projectOverview.noExperimentsYet')}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
