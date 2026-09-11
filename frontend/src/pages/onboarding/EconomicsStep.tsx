import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { ProjectConfig, ProjectConfigPatch } from '../../api/types'
import { formatValidationErrors } from './validationError'

interface Props {
  config: ProjectConfig
  onSave: (patch: ProjectConfigPatch) => Promise<unknown>
  saving: boolean
}

/** Stage 15 task 6: economics is entirely optional -- a project that
 * never maps cost/success/value columns simply never gets an economics
 * section on its release decisions, which is a normal, supported state,
 * not an error. */
export function EconomicsStep({ config, onSave, saving }: Props) {
  const { t } = useTranslation()
  const [costColumn, setCostColumn] = useState(config.economics?.cost_column ?? '')
  const [successColumn, setSuccessColumn] = useState(config.economics?.success_column ?? '')
  const [valueColumn, setValueColumn] = useState(config.economics?.value_column ?? '')
  const [error, setError] = useState<string[] | null>(null)

  const anyFieldFilled = costColumn.trim() || successColumn.trim() || valueColumn.trim()

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (anyFieldFilled && !successColumn.trim()) {
      setError([t('onboarding.economics.errorSuccessRequired')])
      return
    }
    try {
      await onSave({
        economics: anyFieldFilled
          ? { success_column: successColumn.trim(), ...(costColumn.trim() ? { cost_column: costColumn.trim() } : {}), ...(valueColumn.trim() ? { value_column: valueColumn.trim() } : {}) }
          : null,
      })
    } catch (err) {
      setError(formatValidationErrors(err))
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>{t('onboarding.steps.economics')}</h2>
        <p>{t('onboarding.economics.subtitle')}</p>
      </div>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label className="field">
          <span>{t('onboarding.economics.successColumn')}</span>
          <input value={successColumn} onChange={(e) => setSuccessColumn(e.target.value)} className="mono" placeholder={t('onboarding.economics.successColumnPlaceholder')} />
        </label>
        <label className="field">
          <span>{t('onboarding.economics.costColumn')}</span>
          <input value={costColumn} onChange={(e) => setCostColumn(e.target.value)} className="mono" placeholder={t('onboarding.economics.costColumnPlaceholder')} />
        </label>
        <label className="field">
          <span>{t('onboarding.economics.valueColumn')}</span>
          <input value={valueColumn} onChange={(e) => setValueColumn(e.target.value)} className="mono" placeholder={t('onboarding.economics.valueColumnPlaceholder')} />
        </label>
        <p className="text-muted" style={{ fontSize: 12 }}>
          {t('onboarding.economics.note')}
        </p>
        <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={saving}>
          {saving ? t('common.saving') : t('onboarding.economics.save')}
        </button>
      </form>

      {error && <div className="chip chip-negative" style={{ marginTop: 12 }}>{error.join('; ')}</div>}
    </div>
  )
}
