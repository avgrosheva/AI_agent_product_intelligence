import type { Verdict } from '../../api/types'

const LABEL: Record<Verdict, string> = {
  significant: 'Statistically significant',
  not_significant: 'Not significant',
  insufficient_evidence: 'Insufficient evidence',
}

// Deliberately neutral for "not_significant" and "insufficient_evidence"
// (Stage 6 SS10: "Do not use red for every non-significant result" — a
// flat/inconclusive result is not bad news, it is a lack of evidence).
export function VerdictBadge({ verdict, compact = false }: { verdict: Verdict; compact?: boolean }) {
  const cls = verdict === 'significant' ? 'chip-accent' : 'chip-neutral'
  return <span className={`chip ${cls}`}>{compact ? (verdict === 'significant' ? 'Significant' : verdict === 'not_significant' ? 'Not significant' : 'Insufficient data') : LABEL[verdict]}</span>
}
