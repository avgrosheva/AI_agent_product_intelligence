import { humanizeSegmentLabel } from '../../lib/format'

export interface SegmentEffectRow {
  segment_label: string
  excess_contribution: number
}

/** Diverging horizontal bars of each finding's excess contribution to the
 * regression (backend.investigation.scoring: user_share * (segment_delta
 * - overall_delta)), in the same most-significant-first order the
 * findings list is already sorted in. Purpose: which segment(s) actually
 * drive the regression is a comparison across segments, and a column of
 * numbers makes a reviewer do that comparison by eye; a bar makes it
 * immediate.
 *
 * Deliberately a single neutral hue, not a good/bad red-vs-green split:
 * excess_contribution's sign reflects the raw (not direction-adjusted)
 * segment-vs-overall delta for whatever the primary metric is, so a
 * positive value is "bad" for a lower-is-better metric and "good" for a
 * higher-is-better one (release/summary.py had exactly this bug for
 * primary_metric_delta's wording — see that fix). Rather than risk the
 * same class of error here, magnitude and sign (left/right of center)
 * are shown honestly; which side is "bad" is for the finding text next
 * to it to say, not this chart's color. */
export function SegmentEffectChart({ rows }: { rows: SegmentEffectRow[] }) {
  if (rows.length === 0) return null
  const scale = Math.max(...rows.map((r) => Math.abs(r.excess_contribution)), 0.01) * 1.15

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rows.map((r) => {
        const pct = (Math.abs(r.excess_contribution) / scale) * 50
        const isNegative = r.excess_contribution < 0
        return (
          <div key={r.segment_label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 64px', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 500 }} title={r.segment_label}>{humanizeSegmentLabel(r.segment_label)}</span>
            <div style={{ position: 'relative', height: 14, background: 'var(--color-neutral-weak)', borderRadius: 3 }} aria-hidden="true">
              <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--color-border-strong)' }} />
              <div
                style={{
                  position: 'absolute', top: 1, bottom: 1,
                  left: isNegative ? `calc(50% - ${pct}%)` : '50%',
                  width: `${pct}%`,
                  background: 'var(--color-accent)',
                  borderRadius: 2,
                }}
              />
            </div>
            <span className="mono text-secondary" style={{ fontSize: 11.5, textAlign: 'right' }}>
              {(r.excess_contribution * 100).toFixed(1)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}
