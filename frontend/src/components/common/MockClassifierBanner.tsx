import { useTranslation } from 'react-i18next'
import type { ClassifierProvenance } from '../../api/types'

/** Mandatory disclaimer (Stage 6 SS8 / Stage 3 review requirement #2): a
 * mock classifier's numbers must never be presentable as real-LLM
 * performance. Rendered from `is_mock`, not from a hardcoded assumption —
 * if a real AnthropicLLMClient run is ever loaded, this banner disappears
 * on its own because `is_mock` will be false. */
export function MockClassifierBanner({ provenance }: { provenance: ClassifierProvenance }) {
  const { t } = useTranslation()
  if (!provenance.is_mock) return null
  return (
    <div
      role="note"
      className="card"
      style={{ background: 'var(--color-warning-weak)', borderColor: 'var(--color-warning)', display: 'flex', gap: 10, alignItems: 'flex-start', padding: '12px 16px' }}
    >
      <span aria-hidden="true" style={{ color: 'var(--color-warning)', fontWeight: 700 }}>!</span>
      <div style={{ fontSize: 12.5, color: 'var(--color-text)' }}>
        <strong>{t('mockClassifierBanner.title')}</strong>{' '}
        {t('mockClassifierBanner.body', { version: provenance.classifier_version ?? t('mockClassifierBanner.unversioned') })}
      </div>
    </div>
  )
}
