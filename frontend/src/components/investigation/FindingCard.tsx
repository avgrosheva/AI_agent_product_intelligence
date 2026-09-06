import { Link } from 'react-router-dom'
import type { Finding, InvestigationLens } from '../../api/types'
import { formatDelta, formatMetricValue, formatPValue, humanizeSegmentLabel } from '../../lib/format'
import { sessionsUrlForSegment } from '../../lib/sessionLink'
import { isAndroidLatencySegment } from '../../lib/knownMechanisms'

interface Props {
  finding: Finding
  metricName: string
  experimentId: string
  selected: boolean
  onSelect: () => void
}

export function FindingCard({ finding, metricName, experimentId, selected, onSelect }: Props) {
  const isLatency = isAndroidLatencySegment(finding)
  const mechanismLabel = isLatency
    ? 'Elevated latency (non-conversational)'
    : (finding.dominant_failure_mode ?? 'none dominant')

  return (
    <div
      className="card"
      style={{
        padding: '14px 16px', cursor: 'pointer',
        borderColor: selected ? 'var(--color-accent)' : undefined,
        boxShadow: selected ? '0 0 0 1px var(--color-accent)' : undefined,
      }}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelect() }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{humanizeSegmentLabel(finding.segment_label)}</div>
          <div className="text-muted" style={{ fontSize: 11.5, marginTop: 2 }}>
            v1 {formatMetricValue(metricName, finding.cluster_mean_v1)} → v2 {formatMetricValue(metricName, finding.cluster_mean_v2)}
            {' '}({formatDelta(metricName, finding.cluster_mean_v1, finding.cluster_mean_v2)})
          </div>
        </div>
        <span className="chip chip-accent">p = {formatPValue(finding.p_value)}</span>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10, flexWrap: 'wrap', fontSize: 12 }} className="text-secondary">
        <span>excess contribution: <strong className="mono">{(finding.excess_contribution * 100).toFixed(1)}%</strong></span>
        {finding.effect_size_value !== null && <span>effect size: <strong className="mono">{finding.effect_size_value.toFixed(2)}</strong></span>}
        <span>mechanism: <strong>{mechanismLabel}</strong></span>
      </div>
      <Link
        to={sessionsUrlForSegment(experimentId, finding.segment_filter)}
        className="btn btn-small"
        style={{ marginTop: 10 }}
        onClick={(e) => e.stopPropagation()}
      >
        View sessions →
      </Link>
    </div>
  )
}

export function lensHeadline(lens: InvestigationLens, finding: Finding | undefined): string {
  if (!finding) return 'No segment passed the significance and minimum-effect-size filters for this lens.'
  const seg = humanizeSegmentLabel(finding.segment_label)
  const verb = lens === 'abandonment' ? 'abandonment is concentrated in' : lens === 'conversion' ? 'conversion movement is concentrated in' : 'constraint-satisfaction change is concentrated in'
  return `v2 ${verb} ${seg}.`
}
