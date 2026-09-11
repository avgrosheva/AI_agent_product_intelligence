import type { ReleaseEvaluation } from '../../api/types'
import { formatDateTime } from '../../lib/format'

const VERDICT_COLOR: Record<string, string> = {
  SHIP: 'var(--color-positive)',
  HOLD: 'var(--color-warning)',
  ROLLBACK: 'var(--color-negative)',
}

/** This experiment's verdict across its past release evaluations, oldest
 * to newest. Purpose: a single point-in-time decision card can't show
 * whether today's regression is new or has been persistent across
 * repeated checks (e.g. under scheduled monitoring) -- that distinction
 * directly informs whether "hold and re-check" or "roll back now" is the
 * right call, and it's exactly what a released-decision screen with no
 * memory of past evaluations can't answer. Verdict, not a metric value,
 * is what's plotted: ReleaseEvaluation carries no typed primary-metric-
 * delta field (only an untyped key_metrics dict), and status colors are
 * the one place in this app where color already means a specific state
 * (SHIP/HOLD/ROLLBACK), not a claim this chart would be inventing. */
export function ReleaseTrendChart({ evaluations }: { evaluations: ReleaseEvaluation[] }) {
  if (evaluations.length < 2) return null
  const ordered = [...evaluations].sort((a, b) => a.evaluated_at.localeCompare(b.evaluated_at))

  return (
    <div>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', height: 28 }}>
        <div style={{ position: 'absolute', left: 8, right: 8, top: '50%', height: 2, background: 'var(--color-border)', transform: 'translateY(-50%)' }} />
        <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', width: '100%' }}>
          {ordered.map((e) => (
            <div
              key={e.evaluation_id}
              title={`${e.status} · ${formatDateTime(e.evaluated_at)}`}
              style={{
                width: 12, height: 12, borderRadius: '50%', background: VERDICT_COLOR[e.status] ?? 'var(--color-neutral)',
                border: '2px solid var(--color-surface)', boxShadow: '0 0 0 1px var(--color-border-strong)',
              }}
            />
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <span className="text-muted" style={{ fontSize: 10.5 }}>{formatDateTime(ordered[0].evaluated_at)}</span>
        <span className="text-muted" style={{ fontSize: 10.5 }}>{formatDateTime(ordered[ordered.length - 1].evaluated_at)}</span>
      </div>
    </div>
  )
}
