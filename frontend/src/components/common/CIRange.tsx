interface CIRangeProps {
  low: number
  high: number
  estimate?: number
  formatValue: (v: number) => string
}

/** Forest-plot-style confidence interval: a track from low to high, a dot
 * at the point estimate, and a reference line at zero (no difference). */
export function CIRange({ low, high, estimate, formatValue }: CIRangeProps) {
  const point = estimate ?? (low + high) / 2
  const span = Math.max(high - low, 1e-9)
  const pad = span * 0.6
  const domainMin = Math.min(low, 0) - pad
  const domainMax = Math.max(high, 0) + pad
  const toPct = (v: number) => ((v - domainMin) / (domainMax - domainMin)) * 100

  const crossesZero = low <= 0 && high >= 0

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
      <div style={{ position: 'relative', flex: 1, height: 16 }} aria-hidden="true">
        <div
          style={{
            position: 'absolute', top: '50%', left: 0, right: 0, height: 1, background: 'var(--color-border-strong)', transform: 'translateY(-50%)',
          }}
        />
        <div
          style={{
            position: 'absolute', left: `${toPct(0)}%`, top: 0, bottom: 0, width: 1, background: 'var(--color-text-muted)',
          }}
          title="No difference"
        />
        <div
          style={{
            position: 'absolute', left: `${toPct(low)}%`, width: `${toPct(high) - toPct(low)}%`, top: '50%',
            height: 3, background: crossesZero ? 'var(--color-neutral)' : 'var(--color-accent)', transform: 'translateY(-50%)', borderRadius: 2,
          }}
        />
        <div
          style={{
            position: 'absolute', left: `${toPct(point)}%`, top: '50%', width: 7, height: 7, borderRadius: '50%',
            background: crossesZero ? 'var(--color-neutral)' : 'var(--color-accent)', transform: 'translate(-50%, -50%)',
          }}
        />
      </div>
      <span className="text-secondary mono" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
        {formatValue(low)} to {formatValue(high)}
      </span>
    </div>
  )
}
