import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Recommendation } from '../../api/types'

const VERDICT_META: Record<Recommendation['verdict'], { label: string; cls: string }> = {
  ship: { label: 'SHIP', cls: 'chip-positive' },
  hold: { label: 'HOLD', cls: 'chip-warning' },
  roll_back: { label: 'ROLL BACK', cls: 'chip-negative' },
}

/** Renders the backend's deterministic rule-based verdict. Explicitly
 * labeled "Decision rule result" (Stage 6 SS9) so it never reads as an
 * LLM opinion — the rules_applied list (collapsed by default) is the
 * literal rule text from backend.investigation.recommend, not a summary
 * this component writes. */
export function RecommendationPanel({ recommendation }: { recommendation: Recommendation }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const meta = VERDICT_META[recommendation.verdict]

  return (
    <div className="card" style={{ borderColor: recommendation.verdict === 'hold' ? 'var(--color-warning)' : undefined }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <span className={`chip ${meta.cls}`} style={{ fontSize: 14, padding: '5px 14px' }}>{meta.label}</span>
        <span className="text-muted" style={{ fontSize: 11.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {t('recommendationPanel.decisionRuleResult')}
        </span>
      </div>
      <p style={{ fontSize: 13.5, marginBottom: 10 }}>{recommendation.primary_reason}</p>
      <p style={{ fontSize: 13, marginBottom: 4 }}><strong>{t('recommendationPanel.nextAction')}</strong> {recommendation.next_action}</p>
      {recommendation.blocking_guardrails.length > 0 && (
        <p style={{ fontSize: 13 }}>
          <strong>{t('recommendationPanel.blockingGuardrails')}</strong> {recommendation.blocking_guardrails.join(', ')}
        </p>
      )}
      <button type="button" className="btn btn-small" style={{ marginTop: 10 }} onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
        {expanded ? t('recommendationPanel.hideDecisionRules') : t('recommendationPanel.showDecisionRules')}
      </button>
      {expanded && (
        <ul style={{ marginTop: 10, paddingLeft: 18, fontSize: 12.5 }} className="text-secondary">
          {recommendation.rules_applied.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
