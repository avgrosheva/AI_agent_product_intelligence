import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MetricResult } from '../../api/types'
import { formatDelta, formatMetricValue, formatPValue, humanizeMetricName } from '../../lib/format'
import { deltaDirection } from '../../lib/metricPolarity'
import { CIRange } from './CIRange'
import { VerdictBadge } from './VerdictBadge'

const DIRECTION_CLASS: Record<'good' | 'bad' | 'neutral', string> = {
  good: 'chip-positive',
  bad: 'chip-negative',
  neutral: 'chip-neutral',
}

/** One metric's v1-vs-v2 readout: values, delta (colored by whether it's
 * good/bad news for this metric), verdict, and an expandable detail row
 * for p-value / effect size / CI — kept out of the default view per
 * Stage 6 SS4B ("a reviewer should understand the result without reading
 * p-values everywhere"). */
export function MetricComparisonRow({ metric, showName = true }: { metric: MetricResult; showName?: boolean }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const v1 = metric.cluster_mean_v1 ?? metric.session_value_v1
  const v2 = metric.cluster_mean_v2 ?? metric.session_value_v2
  const direction = deltaDirection(metric.metric_name, v1, v2)
  const hasDetail = metric.p_value !== null || metric.ci_low !== null

  return (
    <div className="card" style={{ padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        {showName && (
          <div style={{ minWidth: 200, flex: '0 0 200px' }}>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>{humanizeMetricName(metric.metric_name)}</div>
            <div className="text-muted" style={{ fontSize: 11.5 }}>{metric.semantic_class.replace(/_/g, ' ')}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 20, flex: 1, minWidth: 220 }}>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v1')}</div>
            <div className="mono" style={{ fontSize: 13.5 }}>{formatMetricValue(metric.metric_name, v1)}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('common.v2')}</div>
            <div className="mono" style={{ fontSize: 13.5 }}>{formatMetricValue(metric.metric_name, v2)}</div>
          </div>
          <div>
            <div className="text-muted" style={{ fontSize: 11 }}>{t('common.delta')}</div>
            <span className={`chip ${DIRECTION_CLASS[direction]}`}>{formatDelta(metric.metric_name, v1, v2)}</span>
          </div>
        </div>
        <VerdictBadge verdict={metric.verdict} compact />
        {hasDetail && (
          <button
            type="button"
            className="btn btn-small"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
          >
            {expanded ? t('common.hideDetail') : t('common.detail')}
          </button>
        )}
      </div>
      {expanded && hasDetail && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', fontSize: 12 }} className="text-secondary">
            {metric.test_name && <span>{t('metricRow.test', { name: metric.test_name })}</span>}
            {metric.p_value !== null && <span>p = {formatPValue(metric.p_value)}</span>}
            {metric.effect_size_name && metric.effect_size_value !== null && (
              <span>{metric.effect_size_name} = {metric.effect_size_value.toFixed(3)}</span>
            )}
            <span>{t('metricRow.usersCount', { n1: metric.n_users_v1.toLocaleString('en-US'), n2: metric.n_users_v2.toLocaleString('en-US') })}</span>
          </div>
          {metric.ci_low !== null && metric.ci_high !== null && (
            <CIRange low={metric.ci_low} high={metric.ci_high} formatValue={(v) => formatDelta(metric.metric_name, 0, v)} />
          )}
          {metric.notes.length > 0 && (
            <div className="text-muted" style={{ fontSize: 11.5 }}>{metric.notes.join(' · ')}</div>
          )}
        </div>
      )}
    </div>
  )
}
