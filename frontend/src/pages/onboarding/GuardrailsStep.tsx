import { useState, type FormEvent } from 'react'
import type { AvailableGuardrail, GuardrailConfigEntry, ProjectConfig, ProjectConfigPatch } from '../../api/types'
import { formatValidationErrors } from './validationError'

const AGGREGATIONS = ['p95_raw', 'cluster_mean']
const KINDS = ['ratio', 'absolute']
const DIRECTIONS = ['increase_is_bad', 'decrease_is_bad']
const SEVERITIES = ['blocking', 'warning']

function toEntry(g: AvailableGuardrail): GuardrailConfigEntry {
  return { name: g.name, metric: g.metric, column: g.column, aggregation: g.aggregation, kind: g.kind, direction: g.direction, threshold: g.threshold, severity: g.severity, enabled: g.enabled }
}

interface Props {
  config: ProjectConfig
  onSave: (patch: ProjectConfigPatch) => Promise<unknown>
  saving: boolean
}

export function GuardrailsStep({ config, onSave, saving }: Props) {
  const [showAddForm, setShowAddForm] = useState(false)
  const [name, setName] = useState('')
  const [metric, setMetric] = useState('')
  const [column, setColumn] = useState('')
  const [aggregation, setAggregation] = useState('cluster_mean')
  const [kind, setKind] = useState('absolute')
  const [direction, setDirection] = useState('increase_is_bad')
  const [threshold, setThreshold] = useState('')
  const [severity, setSeverity] = useState('blocking')
  const [error, setError] = useState<string[] | null>(null)

  async function persist(list: GuardrailConfigEntry[]) {
    setError(null)
    try {
      await onSave({ guardrails: { guardrails: list } })
    } catch (err) {
      setError(formatValidationErrors(err))
    }
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    const parsedThreshold = Number(threshold)
    if (Number.isNaN(parsedThreshold)) {
      setError(['threshold: must be a number'])
      return
    }
    const newEntry: GuardrailConfigEntry = { name, metric, column, aggregation, kind, direction, threshold: parsedThreshold, severity, enabled: true }
    const list = [...config.available_guardrails.map(toEntry), newEntry]
    await persist(list)
    setName('')
    setColumn('')
    setThreshold('')
    setShowAddForm(false)
  }

  async function toggleEnabled(target: AvailableGuardrail) {
    const list = config.available_guardrails.map((g) => (g.name === target.name ? { ...toEntry(g), enabled: !g.enabled } : toEntry(g)))
    await persist(list)
  }

  async function removeGuardrail(target: AvailableGuardrail) {
    const list = config.available_guardrails.filter((g) => g.name !== target.name).map(toEntry)
    await persist(list)
  }

  async function resetToDefaults() {
    setError(null)
    try {
      await onSave({ guardrails: null })
    } catch (err) {
      setError(formatValidationErrors(err))
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Guardrails</h2>
        <p>Automatic checks that can block a ship decision when a metric moves too far in the wrong direction.</p>
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Metric</th>
              <th>Column</th>
              <th>Threshold</th>
              <th>Direction</th>
              <th>Severity</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {config.available_guardrails.map((g) => (
              <tr key={g.name}>
                <td className="mono">{g.name}</td>
                <td>{g.metric || '—'}</td>
                <td className="mono">{g.column}</td>
                <td>{g.threshold}</td>
                <td>{g.direction}</td>
                <td>
                  <span className={`chip ${g.severity === 'blocking' ? 'chip-negative' : 'chip-warning'}`}>{g.severity}</span>
                </td>
                <td>
                  <span className={`chip ${g.enabled ? 'chip-positive' : 'chip-neutral'}`}>{g.enabled ? 'Enabled' : 'Disabled'}</span>
                </td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button type="button" className="btn btn-small" onClick={() => toggleEnabled(g)} disabled={saving}>
                    {g.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button type="button" className="btn btn-small" onClick={() => removeGuardrail(g)} disabled={saving}>Remove</button>
                </td>
              </tr>
            ))}
            {config.available_guardrails.length === 0 && (
              <tr><td colSpan={8} className="text-muted">No guardrails configured.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        {!showAddForm && <button type="button" className="btn btn-small" onClick={() => setShowAddForm(true)}>+ Add a guardrail</button>}
        {config.guardrails !== null && <button type="button" className="btn btn-small" onClick={resetToDefaults} disabled={saving}>Reset to domain defaults</button>}
      </div>

      {showAddForm && (
        <form onSubmit={handleAdd} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14, borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
          <div className="grid-3">
            <label className="field">
              <span>Name (unique)</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </label>
            <label className="field">
              <span>Watches metric</span>
              <select value={metric} onChange={(e) => setMetric(e.target.value)}>
                <option value="">-- optional, descriptive only --</option>
                {config.available_metrics.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Data column</span>
              <input value={column} onChange={(e) => setColumn(e.target.value)} required placeholder="e.g. handle_time_seconds" />
            </label>
            <label className="field">
              <span>Aggregation</span>
              <select value={aggregation} onChange={(e) => setAggregation(e.target.value)}>
                {AGGREGATIONS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Comparison</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Threshold</span>
              <input value={threshold} onChange={(e) => setThreshold(e.target.value)} required type="number" step="any" />
            </label>
            <label className="field">
              <span>Direction</span>
              <select value={direction} onChange={(e) => setDirection(e.target.value)}>
                {DIRECTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Severity</span>
              <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Add guardrail'}</button>
            <button type="button" className="btn" onClick={() => setShowAddForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      {error && <div className="chip chip-negative" style={{ marginTop: 12 }}>{error.join('; ')}</div>}
    </div>
  )
}
