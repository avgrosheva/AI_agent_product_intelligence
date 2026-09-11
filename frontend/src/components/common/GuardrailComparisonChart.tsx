import { useTranslation } from 'react-i18next'
import type { GenericGuardrailCheck } from '../../api/types'

/** Per-guardrail v1-vs-v2 bar comparison, one row per check. Each row is
 * scaled to its own max(v1,v2) rather than a single shared scale -- units
 * differ wildly across guardrails (a latency in ms, a rate in [0,1], a
 * dollar cost), so one shared axis would flatten most rows unreadable.
 * Purpose: at a glance, which guardrails are close to breaching, not just
 * a breached=yes/no chip -- a guardrail at 95% of its threshold and one
 * at 20% both render as "ok" in text but look very different here, which
 * is exactly the signal that should inform a ship/hold call before a
 * guardrail actually trips. */
export function GuardrailComparisonChart({ checks }: { checks: GenericGuardrailCheck[] }) {
  const { t } = useTranslation()
  if (checks.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {checks.map((c) => {
        const scale = Math.max(c.v1_value, c.v2_value, 1e-9) * 1.15
        const v1Pct = (c.v1_value / scale) * 100
        const v2Pct = (c.v2_value / scale) * 100
        return (
          <div key={c.name}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{c.name.replace(/_/g, ' ')}</span>
              <span className={`chip ${c.breached ? 'chip-negative' : 'chip-neutral'}`} style={{ fontSize: 10 }}>
                {c.breached ? t('guardrailChart.breached') : t('guardrailChart.ok')}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="text-muted" style={{ fontSize: 10.5, width: 16 }}>v1</span>
                <div style={{ flex: 1, height: 10, background: 'var(--color-neutral-weak)', borderRadius: 3 }}>
                  <div style={{ width: `${v1Pct}%`, height: '100%', background: 'var(--color-neutral)', borderRadius: 3 }} />
                </div>
                <span className="mono text-secondary" style={{ fontSize: 11, width: 68, textAlign: 'right' }}>{c.v1_value.toFixed(3)}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="text-muted" style={{ fontSize: 10.5, width: 16 }}>v2</span>
                <div style={{ flex: 1, height: 10, background: 'var(--color-neutral-weak)', borderRadius: 3 }}>
                  <div
                    style={{
                      width: `${v2Pct}%`, height: '100%', borderRadius: 3,
                      // Stage 20: never the brand accent here -- "not
                      // breached" is a neutral state (same "ok is not
                      // exciting good news" call as the chip beside it
                      // being chip-neutral, not chip-positive), and using
                      // the brand's violet for a status would blur the
                      // line between UI chrome and guardrail health.
                      background: c.breached ? 'var(--color-negative)' : 'var(--color-neutral)',
                    }}
                  />
                </div>
                <span className="mono text-secondary" style={{ fontSize: 11, width: 68, textAlign: 'right' }}>{c.v2_value.toFixed(3)}</span>
              </div>
            </div>
            <div className="text-muted" style={{ fontSize: 10.5, marginTop: 3 }}>{c.threshold_description}</div>
          </div>
        )
      })}
    </div>
  )
}
