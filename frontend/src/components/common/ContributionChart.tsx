import { formatPercent } from '../../lib/format'

export interface ContributionRow {
  label: string
  share: number | null // may exceed 1.0 (100%) or be negative — never clamp/normalize
  note?: string
}

/** Horizontal contribution bars centered on zero. Deliberately not a pie
 * chart (Stage 6 SS5D): excess-abandonment shares can exceed 100% or be
 * negative (offsetting contributions), which a pie cannot represent
 * honestly. Bars are scaled to the largest |share| in the set, with a
 * fixed center line at zero so over-100%/negative values stay legible. */
export function ContributionChart({ rows }: { rows: ContributionRow[] }) {
  const scale = Math.max(...rows.map((r) => Math.abs(r.share ?? 0)), 0.01) * 1.15

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {rows.map((row) => {
        const pct = row.share === null ? 0 : (Math.abs(row.share) / scale) * 50
        const isNegative = (row.share ?? 0) < 0
        return (
          <div key={row.label} style={{ display: 'grid', gridTemplateColumns: '170px 1fr 70px', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12.5, fontWeight: 500 }} title={row.label}>{row.label}</span>
            <div style={{ position: 'relative', height: 16, background: 'var(--color-neutral-weak)', borderRadius: 3 }}>
              <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--color-border-strong)' }} />
              {row.share !== null && (
                <div
                  style={{
                    position: 'absolute',
                    top: 1,
                    bottom: 1,
                    left: isNegative ? `calc(50% - ${pct}%)` : '50%',
                    width: `${pct}%`,
                    background: isNegative ? 'var(--color-positive)' : 'var(--color-negative)',
                    borderRadius: 2,
                  }}
                />
              )}
            </div>
            <span className="mono text-secondary" style={{ fontSize: 12, textAlign: 'right' }}>
              {row.share === null ? 'n/a' : formatPercent(row.share)}
            </span>
            {row.note && (
              <span className="text-muted" style={{ gridColumn: '1 / -1', fontSize: 11 }}>{row.note}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
