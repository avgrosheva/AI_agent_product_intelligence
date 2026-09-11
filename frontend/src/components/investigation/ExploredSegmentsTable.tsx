import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ExploredSegmentSummary } from '../../api/types'
import { formatPValue, humanizeSegmentLabel } from '../../lib/format'

/** Full scan transparency, collapsed by default (Stage 6 SS5B: "Do not
 * show raw 57-segment scan by default. Provide a secondary 'Explored
 * segments' section for completeness."). */
export function ExploredSegmentsTable({ segments }: { segments: ExploredSegmentSummary[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="btn btn-small"
      >
        {t(open ? 'exploredSegments.hideExplored' : 'exploredSegments.showExplored', { count: segments.length })}
      </button>
      {open && (
        <div className="table-scroll" style={{ marginTop: 14 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('exploredSegments.segment')}</th>
                <th>{t('exploredSegments.pValue')}</th>
                <th>{t('exploredSegments.bhSignificant')}</th>
                <th>{t('exploredSegments.meetsMinEffect')}</th>
                <th>{t('exploredSegments.verdict')}</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((s) => (
                <tr key={s.segment_label}>
                  <td>{humanizeSegmentLabel(s.segment_label)}</td>
                  <td className="mono">{formatPValue(s.p_value)}</td>
                  <td>{s.bh_significant ? t('exploredSegments.yes') : t('exploredSegments.no')}</td>
                  <td>{s.meets_min_effect ? t('exploredSegments.yes') : t('exploredSegments.no')}</td>
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
