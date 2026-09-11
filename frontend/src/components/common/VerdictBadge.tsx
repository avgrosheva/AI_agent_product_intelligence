import { useTranslation } from 'react-i18next'
import type { Verdict } from '../../api/types'

const LABEL_KEY: Record<Verdict, string> = {
  significant: 'verdict.significantFull',
  not_significant: 'verdict.notSignificantFull',
  insufficient_evidence: 'verdict.insufficientEvidenceFull',
}

const COMPACT_LABEL_KEY: Record<Verdict, string> = {
  significant: 'verdict.significantCompact',
  not_significant: 'verdict.notSignificantCompact',
  insufficient_evidence: 'verdict.insufficientDataCompact',
}

// Deliberately neutral for "not_significant" and "insufficient_evidence"
// (Stage 6 SS10: "Do not use red for every non-significant result" — a
// flat/inconclusive result is not bad news, it is a lack of evidence).
export function VerdictBadge({ verdict, compact = false }: { verdict: Verdict; compact?: boolean }) {
  const { t } = useTranslation()
  const cls = verdict === 'significant' ? 'chip-accent' : 'chip-neutral'
  return <span className={`chip ${cls}`}>{t(compact ? COMPACT_LABEL_KEY[verdict] : LABEL_KEY[verdict])}</span>
}
