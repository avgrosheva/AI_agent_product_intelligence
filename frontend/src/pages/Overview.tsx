import { Link } from 'react-router-dom'
import { useInvestigation } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { VerdictBadge } from '../components/common/VerdictBadge'
import { formatDelta, formatMetricValue, formatPValue, humanizeMetricName } from '../lib/format'
import { deltaDirection } from '../lib/metricPolarity'
import { useActiveExperiment } from '../state/ActiveExperimentContext'

const STATUS_META: Record<string, { label: string; cls: string }> = {
  ambiguous_investigate: { label: 'Requires investigation', cls: 'chip-warning' },
  no_regression_detected: { label: 'No regression detected', cls: 'chip-positive' },
  not_yet_investigated: { label: 'Not yet investigated', cls: 'chip-neutral' },
}

function SignalCard({
  kicker, metricName, v1, v2, verdict, pValue,
}: {
  kicker: string
  metricName: string
  v1: number | null
  v2: number | null
  verdict: 'significant' | 'not_significant' | 'insufficient_evidence'
  pValue: number | null
}) {
  const direction = deltaDirection(metricName, v1, v2)
  const directionCls = direction === 'good' ? 'chip-positive' : direction === 'bad' ? 'chip-negative' : 'chip-neutral'
  return (
    <div className="card">
      <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
        {kicker}
      </div>
      <h3 style={{ marginBottom: 10 }}>{humanizeMetricName(metricName)}</h3>
      <div style={{ display: 'flex', gap: 18, marginBottom: 10 }}>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>v1</div>
          <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{formatMetricValue(metricName, v1)}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>v2</div>
          <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{formatMetricValue(metricName, v2)}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: 11 }}>delta</div>
          <span className={`chip ${directionCls}`}>{formatDelta(metricName, v1, v2)}</span>
        </div>
      </div>
      <VerdictBadge verdict={verdict} />
      <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>p = {formatPValue(pValue)}</div>
    </div>
  )
}

export function Overview() {
  const { activeExperimentId, activeExperiment, isLoading: expLoading, error: expError } = useActiveExperiment()
  const { data: inv, isLoading: invLoading, error: invError } = useInvestigation(activeExperimentId ?? undefined, 'abandonment')

  if (expLoading) return <div className="page"><LoadingState label="Loading experiments…" /></div>
  if (expError) return <div className="page"><ErrorState message={expError} /></div>
  if (!activeExperiment) return <div className="page"><EmptyState>No experiments found.</EmptyState></div>

  const statusMeta = STATUS_META[activeExperiment.status_chip]
  const northStar = activeExperiment.north_star_metric

  return (
    <div className="page">
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <h1>{activeExperiment.name}</h1>
          <span className={`chip ${statusMeta.cls}`}>{statusMeta.label}</span>
        </div>
        <p className="text-secondary">
          {activeExperiment.control_version} (control) vs {activeExperiment.treatment_version} (treatment) ·{' '}
          {activeExperiment.n_users.toLocaleString('en-US')} users · {activeExperiment.n_sessions.toLocaleString('en-US')} sessions
        </p>
      </div>

      <div className="grid-3">
        <SignalCard
          kicker="Business outcome · North star"
          metricName={northStar.metric_name}
          v1={northStar.cluster_mean_v1}
          v2={northStar.cluster_mean_v2}
          verdict={northStar.verdict}
          pValue={northStar.p_value}
        />
        {invLoading && <div className="card"><LoadingState /></div>}
        {invError && <div className="card"><ErrorState message={(invError as Error).message} /></div>}
        {inv && (
          <SignalCard
            kicker="AI / product behavior · Primary regression signal"
            metricName={inv.overall.metric_name}
            v1={inv.overall.cluster_mean_v1}
            v2={inv.overall.cluster_mean_v2}
            verdict={inv.overall.verdict}
            pValue={inv.overall.p_value}
          />
        )}
        {inv && (
          <div className="card">
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
              Guardrails
            </div>
            <h3 style={{ marginBottom: 10 }}>{inv.any_guardrail_breach ? 'Breach detected' : 'All within threshold'}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {inv.guardrails.map((g) => (
                <div key={g.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
                  <span>{g.name.replace(/_/g, ' ')}</span>
                  <span className={`chip ${g.breached ? 'chip-negative' : 'chip-neutral'}`} style={{ fontSize: 10.5 }}>
                    {g.breached ? 'breached' : 'ok'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {inv && (
        <div className="card">
          <h2 style={{ marginBottom: 10 }}>Summary</h2>
          <p style={{ fontSize: 13.5, lineHeight: 1.7 }}>
            {northStar.verdict === 'significant' ? 'Conversion moved with statistical significance.' : 'Conversion is broadly flat / inconclusive at the aggregate level (not statistically significant).'}{' '}
            {inv.overall.verdict === 'significant' && (inv.overall.cluster_mean_v2 ?? 0) > (inv.overall.cluster_mean_v1 ?? 0)
              ? 'Abandonment is significantly higher in v2 overall.'
              : 'Abandonment shows no clear aggregate regression.'}{' '}
            {inv.any_guardrail_breach
              ? `A guardrail is breached (${inv.guardrails.filter((g) => g.breached).map((g) => g.name).join(', ')}), which on its own is enough to block a ship decision regardless of the north star.`
              : 'No guardrail is currently breached.'}{' '}
            This combination of a flat headline metric, a mechanism-level regression, and a guardrail breach is exactly the pattern that needs segment-level investigation rather than a snap judgment from the aggregate numbers.
          </p>
          <Link to={activeExperimentId ? `/experiments/${activeExperimentId}/investigation` : '#'} className="btn btn-primary" style={{ marginTop: 14 }}>
            Investigate →
          </Link>
        </div>
      )}
    </div>
  )
}
