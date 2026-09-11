import { useState, type FormEvent } from 'react'
import type { ProjectConfig, ProjectConfigPatch } from '../../api/types'
import { formatValidationErrors } from './validationError'

interface Props {
  config: ProjectConfig
  onSave: (patch: ProjectConfigPatch) => Promise<unknown>
  saving: boolean
}

function initialValues(config: ProjectConfig): Record<string, string> {
  const values: Record<string, string> = {}
  const saved = config.segment_dimensions ?? {}
  for (const field of config.available_context_fields) {
    if (field in saved) values[field] = saved[field].join(', ')
  }
  return values
}

/** Stage 15 task 5: dimensions are picked from real, already-ingested
 * context keys (config.available_context_fields) -- there is no way to
 * type in a field that doesn't exist in this project's data. */
export function SegmentsStep({ config, onSave, saving }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set(Object.keys(initialValues(config))))
  const [values, setValues] = useState<Record<string, string>>(initialValues(config))
  const [error, setError] = useState<string[] | null>(null)

  function toggle(field: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(field)) next.delete(field)
      else next.add(field)
      return next
    })
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const dims: Record<string, string[]> = {}
    for (const field of selected) {
      const list = (values[field] ?? '').split(',').map((v) => v.trim()).filter(Boolean)
      if (list.length === 0) {
        setError([`${field}: enter at least one allowed value (comma-separated) or unselect this dimension`])
        return
      }
      dims[field] = list
    }
    try {
      await onSave({ segment_dimensions: Object.keys(dims).length > 0 ? dims : null })
    } catch (err) {
      setError(formatValidationErrors(err))
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Segments</h2>
        <p>Which fields from your session data should be explored when investigating a regression -- picked from fields already seen in your data.</p>
      </div>

      {config.available_context_fields.length === 0 ? (
        <div className="state-box">No context fields have been seen in ingested data yet. Send some sessions with context data, then come back here.</div>
      ) : (
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {config.available_context_fields.map((field) => (
            <div key={field} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <label className="checkbox-field" style={{ minWidth: 200 }}>
                <input type="checkbox" checked={selected.has(field)} onChange={() => toggle(field)} />
                <span className="mono">{field}</span>
              </label>
              {selected.has(field) && (
                <input
                  style={{ flex: 1 }}
                  value={values[field] ?? ''}
                  onChange={(e) => setValues((prev) => ({ ...prev, [field]: e.target.value }))}
                  placeholder="allowed values, comma-separated"
                  className="mono"
                />
              )}
            </div>
          ))}
          <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }} disabled={saving}>
            {saving ? 'Saving…' : 'Save segments'}
          </button>
        </form>
      )}

      {error && <div className="chip chip-negative" style={{ marginTop: 12 }}>{error.join('; ')}</div>}
    </div>
  )
}
