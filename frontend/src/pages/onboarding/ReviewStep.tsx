import { Link } from 'react-router-dom'
import type { ProjectConfig } from '../../api/types'

export function ReviewStep({ config }: { config: ProjectConfig }) {
  return (
    <div className="card">
      <div className="card-header">
        <h2>Review</h2>
        <p>A summary of what's configured for this project. Come back to any step above at any time to change it.</p>
      </div>
      <table className="data-table">
        <tbody>
          <tr><td>Primary metric</td><td className="mono">{config.primary_metric ?? 'not set'}</td></tr>
          <tr><td>Metrics</td><td>{config.metrics === null ? 'domain defaults' : `${config.metrics.metrics.length} custom metric(s)`}</td></tr>
          <tr><td>Guardrails</td><td>{config.available_guardrails.length} active</td></tr>
          <tr><td>Segments</td><td>{config.segment_dimensions ? Object.keys(config.segment_dimensions).join(', ') : 'none selected'}</td></tr>
          <tr><td>Economics</td><td>{config.economics ? 'mapped' : 'not mapped'}</td></tr>
          <tr><td>Notification events</td><td>{config.enabled_notification_rules.length > 0 ? config.enabled_notification_rules.join(', ') : 'none enabled'}</td></tr>
        </tbody>
      </table>
      <Link to="/project" className="btn btn-primary" style={{ marginTop: 16, alignSelf: 'flex-start' }}>
        Go to project overview
      </Link>
    </div>
  )
}
