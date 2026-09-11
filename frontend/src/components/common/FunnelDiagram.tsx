import type { GenericFunnelSeries } from '../../api/types'

/** Session-based funnel per version, generic over whatever stages the
 * domain's funnel has (Stage 16: previously hardcoded to commerce's
 * impression/click/cart/purchase columns; a support-shaped funnel would
 * have none of those). Conversion-from-previous-stage is computed
 * server-side per stage, not recomputed here. The step-to-step
 * conversion rates are conditional on reaching that step, so they can
 * look similar between v1/v2 even when overall abandonment differs a
 * lot -- the regression shows up as fewer v2 sessions ever reaching the
 * funnel at all, not as worse in-funnel conversion (Stage 6 SS4C). */
export function FunnelDiagram({ series }: { series: GenericFunnelSeries[] }) {
  const maxN = Math.max(...series.map((s) => s.n_sessions), 1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {series.map((s) => (
        <div key={s.agent_version}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>{s.agent_version} · {s.n_sessions.toLocaleString('en-US')} sessions</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {s.stages.map((stage) => {
              const widthPct = Math.max((stage.n_sessions / maxN) * 100, 4)
              return (
                <div key={stage.stage} style={{ flex: 1 }}>
                  <div
                    style={{
                      height: 28, width: `${widthPct}%`, minWidth: 40, background: 'var(--color-accent-weak)',
                      border: '1px solid var(--color-accent)', borderRadius: 4, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 11.5, fontWeight: 600, color: 'var(--color-accent)',
                    }}
                    title={`${stage.stage}: ${stage.n_sessions.toLocaleString('en-US')}`}
                  >
                    {stage.n_sessions.toLocaleString('en-US')}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>
                    {stage.stage}
                    {stage.conversion_from_previous !== null && (
                      <span> · {(stage.conversion_from_previous * 100).toFixed(1)}% of prior step</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
