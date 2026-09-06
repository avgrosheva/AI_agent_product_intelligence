import { useState } from 'react'
import type { ExploredSegmentSummary } from '../../api/types'
import { formatPValue, humanizeSegmentLabel } from '../../lib/format'

/** Full scan transparency, collapsed by default (Stage 6 SS5B: "Do not
 * show raw 57-segment scan by default. Provide a secondary 'Explored
 * segments' section for completeness."). */
export function ExploredSegmentsTable({ segments }: { segments: ExploredSegmentSummary[] }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="btn btn-small"
      >
        {open ? 'Hide' : 'Show'} explored segments ({segments.length})
      </button>
      {open && (
        <div className="table-scroll" style={{ marginTop: 14 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Segment</th>
                <th>p-value</th>
                <th>BH significant</th>
                <th>Meets min. effect</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((s) => (
                <tr key={s.segment_label}>
                  <td>{humanizeSegmentLabel(s.segment_label)}</td>
                  <td className="mono">{formatPValue(s.p_value)}</td>
                  <td>{s.bh_significant ? 'yes' : 'no'}</td>
                  <td>{s.meets_min_effect ? 'yes' : 'no'}</td>
                  <td>{s.verdict.replace(/_/g, ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
