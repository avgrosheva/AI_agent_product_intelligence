import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { AvailableMetric, MetricConfigEntry, ProjectConfig, ProjectConfigPatch } from '../../api/types'
import { humanizeMetricName } from '../../lib/format'
import { formatValidationErrors } from './validationError'

const METRIC_TYPES = ['rate', 'continuous', 'continuous_skewed']
const DIRECTIONS = ['higher_is_better', 'lower_is_better']
const ELIGIBILITY_KINDS = ['none', 'not_null', 'equals', 'gte']

function availableMetricToEntry(m: AvailableMetric): MetricConfigEntry {
  return {
    name: m.name,
    label: m.label,
    type: m.metric_type,
    direction: m.direction,
    is_inferential: m.is_inferential,
    is_descriptive: m.is_descriptive,
    ...(m.value_column ? { value_column: m.value_column } : {}),
  }
}

interface Props {
  config: ProjectConfig
  onSave: (patch: ProjectConfigPatch) => Promise<unknown>
  saving: boolean
}

export function MetricsStep({ config, onSave, saving }: Props) {
  const { t } = useTranslation()
  const [primaryMetric, setPrimaryMetric] = useState(config.primary_metric ?? '')
  const [primaryError, setPrimaryError] = useState<string[] | null>(null)

  const [showAddForm, setShowAddForm] = useState(false)
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')
  const [valueColumn, setValueColumn] = useState('')
  const [metricType, setMetricType] = useState('rate')
  const [direction, setDirection] = useState('higher_is_better')
  const [isInferential, setIsInferential] = useState(true)
  const [isDescriptive, setIsDescriptive] = useState(true)
  const [eligibilityKind, setEligibilityKind] = useState('none')
  const [eligibilityColumn, setEligibilityColumn] = useState('')
  const [eligibilityValue, setEligibilityValue] = useState('')
  const [addError, setAddError] = useState<string[] | null>(null)

  const inferentialMetrics = config.available_metrics.filter((m) => m.is_inferential)

  async function handleSavePrimary(e: FormEvent) {
    e.preventDefault()
    setPrimaryError(null)
    try {
      await onSave({ primary_metric: primaryMetric || null })
    } catch (err) {
      setPrimaryError(formatValidationErrors(err))
    }
  }

  async function handleAddMetric(e: FormEvent) {
    e.preventDefault()
    setAddError(null)
    const entries = config.available_metrics.map(availableMetricToEntry)
    const newEntry: MetricConfigEntry = {
      name,
      label: label || name,
      type: metricType,
      direction,
      is_inferential: isInferential,
      is_descriptive: isDescriptive,
      ...(valueColumn ? { value_column: valueColumn } : {}),
      ...(eligibilityKind !== 'none'
        ? { eligibility: { kind: eligibilityKind, column: eligibilityColumn, ...(eligibilityKind !== 'not_null' ? { value: eligibilityValue } : {}) } }
        : {}),
    }
    try {
      await onSave({ metrics: { metrics: [...entries, newEntry] } })
      setName('')
      setLabel('')
      setValueColumn('')
      setEligibilityKind('none')
      setEligibilityColumn('')
      setEligibilityValue('')
      setShowAddForm(false)
    } catch (err) {
      setAddError(formatValidationErrors(err))
    }
  }

  async function handleResetToDefaults() {
    setAddError(null)
    try {
      await onSave({ metrics: null })
    } catch (err) {
      setAddError(formatValidationErrors(err))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="card">
        <div className="card-header">
          <h2>{t('onboarding.metrics.primaryMetricTitle')}</h2>
          <p>{t('onboarding.metrics.primaryMetricSubtitle')}</p>
        </div>
        <form onSubmit={handleSavePrimary} style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: 1 }}>
            <span>{t('onboarding.metrics.primaryMetricLabel')}</span>
            <select value={primaryMetric} onChange={(e) => setPrimaryMetric(e.target.value)}>
              <option value="">{t('onboarding.metrics.noneSelected')}</option>
              {inferentialMetrics.map((m) => (
                <option key={m.name} value={m.name}>{m.label || humanizeMetricName(m.name)} ({m.name})</option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary" disabled={saving}>{t('common.save')}</button>
        </form>
        {primaryError && <div className="chip chip-negative" style={{ marginTop: 10 }}>{primaryError.join('; ')}</div>}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('onboarding.metrics.title')}</h2>
          <p>
            {config.metrics === null
              ? t('onboarding.metrics.usingDefaults')
              : t('onboarding.metrics.customized')}
          </p>
        </div>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('onboarding.metrics.colName')}</th>
                <th>{t('onboarding.metrics.colLabel')}</th>
                <th>{t('onboarding.metrics.colType')}</th>
                <th>{t('onboarding.metrics.colDirection')}</th>
                <th>{t('onboarding.metrics.colValueColumn')}</th>
                <th>{t('onboarding.metrics.colInferential')}</th>
              </tr>
            </thead>
            <tbody>
              {config.available_metrics.map((m) => (
                <tr key={m.name}>
                  <td className="mono">{m.name}</td>
                  <td>{m.label || humanizeMetricName(m.name)}</td>
                  <td>{m.metric_type}</td>
                  <td>{m.direction}</td>
                  <td className="mono">{m.value_column ?? '—'}</td>
                  <td>{m.is_inferential ? t('common.yes') : t('common.no')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          {!showAddForm && (
            <button type="button" className="btn btn-small" onClick={() => setShowAddForm(true)}>{t('onboarding.metrics.addCustom')}</button>
          )}
          {config.metrics !== null && (
            <button type="button" className="btn btn-small" onClick={handleResetToDefaults} disabled={saving}>{t('onboarding.metrics.resetToDefaults')}</button>
          )}
        </div>

        {showAddForm && (
          <form onSubmit={handleAddMetric} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14, borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
            <div className="grid-2">
              <label className="field">
                <span>{t('onboarding.metrics.metricNameUnique')}</span>
                <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
              </label>
              <label className="field">
                <span>{t('onboarding.metrics.displayLabel')}</span>
                <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={name || t('onboarding.metrics.displayLabelPlaceholder')} />
              </label>
              <label className="field">
                <span>{t('onboarding.metrics.valueColumnInput')}</span>
                <input value={valueColumn} onChange={(e) => setValueColumn(e.target.value)} placeholder={t('onboarding.metrics.valueColumnPlaceholder')} />
              </label>
              <label className="field">
                <span>{t('onboarding.metrics.colType')}</span>
                <select value={metricType} onChange={(e) => setMetricType(e.target.value)}>
                  {METRIC_TYPES.map((mt) => <option key={mt} value={mt}>{mt}</option>)}
                </select>
              </label>
              <label className="field">
                <span>{t('onboarding.metrics.colDirection')}</span>
                <select value={direction} onChange={(e) => setDirection(e.target.value)}>
                  {DIRECTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            </div>
            <div style={{ display: 'flex', gap: 16 }}>
              <label className="checkbox-field">
                <input type="checkbox" checked={isInferential} onChange={(e) => setIsInferential(e.target.checked)} />
                {t('onboarding.metrics.usableAsPrimary')}
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={isDescriptive} onChange={(e) => setIsDescriptive(e.target.checked)} />
                {t('onboarding.metrics.showInTables')}
              </label>
            </div>

            <details>
              <summary style={{ cursor: 'pointer', fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{t('onboarding.metrics.eligibilityOptional')}</summary>
              <div className="grid-3" style={{ marginTop: 10 }}>
                <label className="field">
                  <span>{t('onboarding.metrics.rule')}</span>
                  <select value={eligibilityKind} onChange={(e) => setEligibilityKind(e.target.value)}>
                    {ELIGIBILITY_KINDS.map((k) => <option key={k} value={k}>{k === 'none' ? t('onboarding.metrics.noneIncludeAll') : k}</option>)}
                  </select>
                </label>
                {eligibilityKind !== 'none' && (
                  <label className="field">
                    <span>{t('onboarding.metrics.column')}</span>
                    <input value={eligibilityColumn} onChange={(e) => setEligibilityColumn(e.target.value)} />
                  </label>
                )}
                {(eligibilityKind === 'equals' || eligibilityKind === 'gte') && (
                  <label className="field">
                    <span>{t('onboarding.metrics.value')}</span>
                    <input value={eligibilityValue} onChange={(e) => setEligibilityValue(e.target.value)} />
                  </label>
                )}
              </div>
            </details>

            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? t('common.saving') : t('onboarding.metrics.addMetric')}</button>
              <button type="button" className="btn" onClick={() => setShowAddForm(false)}>{t('common.cancel')}</button>
            </div>
          </form>
        )}

        {addError && <div className="chip chip-negative" style={{ marginTop: 12 }}>{addError.join('; ')}</div>}
      </div>
    </div>
  )
}
