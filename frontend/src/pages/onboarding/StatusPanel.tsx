import type { OnboardingStatus } from '../../api/types'

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

  if (status.ingestion_connected) groups.configured.push('Data ingestion is connected')
  else groups.blocking.push('No data source is connected yet -- nothing can be analyzed')

  if (status.data_received) groups.configured.push('Sessions have been received')
  else groups.blocking.push('No sessions have arrived yet')

  if (status.primary_metric_configured) groups.configured.push('A primary metric is set')
  else groups.blocking.push('No primary metric is set -- release decisions cannot be evaluated')

  if (status.guardrails_configured) groups.configured.push('At least one guardrail is active')
  else groups.missing.push('No guardrails are configured -- risky changes could ship unflagged')

  if (status.data_quality_status === 'healthy') groups.configured.push('Data quality looks healthy')
  else if (status.data_quality_status === 'critical') groups.blocking.push('Data quality is critical -- ship decisions are being held automatically')
  else if (status.data_quality_status === 'warning') groups.missing.push('Data quality has warnings worth reviewing')

  groups.optional.push(status.monitoring_enabled ? 'Scheduled monitoring is enabled' : 'Scheduled monitoring is not set up')
  groups.optional.push(status.notifications_configured ? 'Notifications are configured' : 'Notifications are not set up')

  return groups
}

const GROUP_ORDER: { key: keyof StatusGroups; label: string }[] = [
  { key: 'blocking', label: 'Blocking' },
  { key: 'missing', label: 'Missing' },
  { key: 'configured', label: 'Configured' },
  { key: 'optional', label: 'Optional' },
]

export function StatusPanel({ status, isLoading }: { status: OnboardingStatus | undefined; isLoading: boolean }) {
  if (isLoading) return <div className="state-box">Loading readiness…</div>
  if (!status) return null

  const groups = categorizeStatus(status)

  return (
    <div className="card">
      <div className="card-header">
        <h2>Setup readiness</h2>
        <p>What's configured, what's missing, and what's actively blocking analysis right now.</p>
      </div>
      <div className="status-grid">
        {GROUP_ORDER.map(({ key, label }) => (
          <div key={key} className={`status-group ${key}`}>
            <h4>{label}</h4>
            {groups[key].length === 0 ? (
              <p className="text-muted" style={{ fontSize: 12.5 }}>Nothing here</p>
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
