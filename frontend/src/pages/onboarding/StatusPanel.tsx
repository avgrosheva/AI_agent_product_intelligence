import { useTranslation } from 'react-i18next'
import type { OnboardingStatus } from '../../api/types'
import { i18n } from '../../i18n'

interface StatusGroups {
  blocking: string[]
  configured: string[]
  missing: string[]
  optional: string[]
}

/** Stage 15 task 2: turns the existing onboarding-status endpoint's raw
 * booleans into the four buckets a PM/analyst actually cares about --
 * what's already working, what's still needed, what's actively
 * preventing analysis, and what's optional polish. No new checks are
 * invented here; every line traces back to one field of the real
 * status response. */
export function categorizeStatus(status: OnboardingStatus): StatusGroups {
  const groups: StatusGroups = { blocking: [], configured: [], missing: [], optional: [] }

  if (status.ingestion_connected) groups.configured.push(i18n.t('onboarding.status.ingestionConnected'))
  else groups.blocking.push(i18n.t('onboarding.status.noDataSource'))

  if (status.data_received) groups.configured.push(i18n.t('onboarding.status.sessionsReceived'))
  else groups.blocking.push(i18n.t('onboarding.status.noSessions'))

  if (status.primary_metric_configured) groups.configured.push(i18n.t('onboarding.status.primaryMetricSet'))
  else groups.blocking.push(i18n.t('onboarding.status.noPrimaryMetric'))

  if (status.guardrails_configured) groups.configured.push(i18n.t('onboarding.status.guardrailActive'))
  else groups.missing.push(i18n.t('onboarding.status.noGuardrails'))

  if (status.data_quality_status === 'healthy') groups.configured.push(i18n.t('onboarding.status.dataQualityHealthy'))
  else if (status.data_quality_status === 'critical') groups.blocking.push(i18n.t('onboarding.status.dataQualityCritical'))
  else if (status.data_quality_status === 'warning') groups.missing.push(i18n.t('onboarding.status.dataQualityWarning'))

  groups.optional.push(i18n.t(status.monitoring_enabled ? 'onboarding.status.monitoringEnabled' : 'onboarding.status.monitoringNotSetUp'))
  groups.optional.push(i18n.t(status.notifications_configured ? 'onboarding.status.notificationsConfigured' : 'onboarding.status.notificationsNotSetUp'))

  return groups
}

const GROUP_ORDER: { key: keyof StatusGroups; labelKey: string }[] = [
  { key: 'blocking', labelKey: 'onboarding.status.groupBlocking' },
  { key: 'missing', labelKey: 'onboarding.status.groupMissing' },
  { key: 'configured', labelKey: 'onboarding.status.groupConfigured' },
  { key: 'optional', labelKey: 'onboarding.status.groupOptional' },
]

export function StatusPanel({ status, isLoading }: { status: OnboardingStatus | undefined; isLoading: boolean }) {
  const { t } = useTranslation()
  if (isLoading) return <div className="state-box">{t('onboarding.status.loading')}</div>
  if (!status) return null

  const groups = categorizeStatus(status)

  return (
    <div className="card">
      <div className="card-header">
        <h2>{t('onboarding.status.title')}</h2>
        <p>{t('onboarding.status.subtitle')}</p>
      </div>
      <div className="status-grid">
        {GROUP_ORDER.map(({ key, labelKey }) => (
          <div key={key} className={`status-group ${key}`}>
            <h4>{t(labelKey)}</h4>
            {groups[key].length === 0 ? (
              <p className="text-muted" style={{ fontSize: 12.5 }}>{t('onboarding.status.nothingHere')}</p>
            ) : (
              <ul>
                {groups[key].map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
