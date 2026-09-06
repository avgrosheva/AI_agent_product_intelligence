import type { FunnelStep } from '../../api/types'
import { formatPercent } from '../../lib/format'

const STEPS: { key: keyof FunnelStep; label: string }[] = [
  { key: 'n_impression', label: 'Impression' },
  { key: 'n_click', label: 'Click' },
  { key: 'n_cart', label: 'Add to cart' },
  { key: 'n_purchase', label: 'Purchase' },
]

/** Session-based funnel per version. The step-to-step conversion rates
 * (impression->click etc.) are conditional on reaching that step, so they
 * look similar between v1/v2 even when overall abandonment differs a
 * lot — the regression shows up as fewer v2 sessions ever reaching the
 * funnel at all, not as worse in-funnel conversion (Stage 6 SS4C). */
export function FunnelDiagram({ funnel }: { funnel: FunnelStep[] }) {
  const maxN = Math.max(...funnel.map((f) => f.n_sessions))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {funnel.map((f) => (
        <div key={f.agent_version}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>{f.agent_version} · {f.n_sessions.toLocaleString('en-US')} sessions</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {STEPS.map((step, i) => {
              const n = f[step.key] as number
              const widthPct = Math.max((n / maxN) * 100, 4)
              const rate = i === 0 ? null : ([f.impression_to_click_rate, f.click_to_cart_rate, f.cart_to_purchase_rate][i - 1])
              return (
                <div key={step.key} style={{ flex: 1 }}>
                  <div
                    style={{
                      height: 28, width: `${widthPct}%`, minWidth: 40, background: 'var(--color-accent-weak)',
                      border: '1px solid var(--color-accent)', borderRadius: 4, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 11.5, fontWeight: 600, color: 'var(--color-accent)',
                    }}
                    title={`${step.label}: ${n.toLocaleString('en-US')}`}
                  >
                    {n.toLocaleString('en-US')}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>
                    {step.label}
                    {rate !== null && <span> · {formatPercent(rate)} of prior step</span>}
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
