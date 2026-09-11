import { useState, type FormEvent } from 'react'
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
  const [costColumn, setCostColumn] = useState(config.economics?.cost_column ?? '')
  const [successColumn, setSuccessColumn] = useState(config.economics?.success_column ?? '')
  const [valueColumn, setValueColumn] = useState(config.economics?.value_column ?? '')
  const [error, setError] = useState<string[] | null>(null)

  const anyFieldFilled = costColumn.trim() || successColumn.trim() || valueColumn.trim()

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (anyFieldFilled && !successColumn.trim()) {
      setError(['success_column: required when an economics mapping is provided'])
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
        <h2>Economics</h2>
        <p>Optional. Map columns from your ingested data so release decisions can show a cost/value impact -- leave blank to skip.</p>
      </div>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label className="field">
          <span>Success column (required if mapping economics)</span>
          <input value={successColumn} onChange={(e) => setSuccessColumn(e.target.value)} className="mono" placeholder="e.g. resolved" />
        </label>
        <label className="field">
          <span>Cost column (optional)</span>
          <input value={costColumn} onChange={(e) => setCostColumn(e.target.value)} className="mono" placeholder="e.g. total_cost_usd" />
        </label>
        <label className="field">
          <span>Value / revenue column (optional)</span>
          <input value={valueColumn} onChange={(e) => setValueColumn(e.target.value)} className="mono" placeholder="e.g. order_value_usd" />
        </label>
        <p className="text-muted" style={{ fontSize: 12 }}>
          Economics will stay unavailable on release decisions until a success column is mapped here and your ingested sessions actually contain that column.
        </p>
        <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={saving}>
          {saving ? 'Saving…' : 'Save economics mapping'}
        </button>
      </form>

      {error && <div className="chip chip-negative" style={{ marginTop: 12 }}>{error.join('; ')}</div>}
    </div>
  )
}
