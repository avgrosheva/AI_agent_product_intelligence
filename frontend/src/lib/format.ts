// Pure display formatting only — no statistics computed here. Every
// number passed in already came from the FastAPI response.

const RATE_METRIC_HINTS = ['rate', 'success']

export function looksLikeRate(metricName: string, v1: number | null, v2: number | null): boolean {
  const nameHint = RATE_METRIC_HINTS.some((h) => metricName.includes(h))
  const rangeHint = (v1 === null || (v1 >= 0 && v1 <= 1)) && (v2 === null || (v2 >= 0 && v2 <= 1))
  return nameHint && rangeHint
}

export function formatMetricValue(metricName: string, value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (looksLikeRate(metricName, value, value)) return `${(value * 100).toFixed(1)}%`
  if (metricName.includes('usd')) return `$${value.toFixed(value < 1 ? 4 : 2)}`
  if (metricName.includes('ms')) return `${Math.round(value).toLocaleString('en-US')} ms`
  if (Math.abs(value) < 10) return value.toFixed(2)
  return value.toLocaleString('en-US', { maximumFractionDigits: 1 })
}

export function formatDelta(metricName: string, v1: number | null, v2: number | null): string {
  if (v1 === null || v2 === null) return '—'
  const delta = v2 - v1
  const sign = delta > 0 ? '+' : ''
  if (looksLikeRate(metricName, v1, v2)) return `${sign}${(delta * 100).toFixed(1)}pp`
  if (metricName.includes('usd')) return `${sign}$${delta.toFixed(delta !== 0 && Math.abs(delta) < 1 ? 4 : 2)}`
  if (metricName.includes('ms')) return `${sign}${Math.round(delta).toLocaleString('en-US')} ms`
  return `${sign}${delta.toFixed(2)}`
}

export function formatPercent(value: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatPValue(p: number | null): string {
  if (p === null || p === undefined) return '—'
  if (p < 0.0001) return p.toExponential(1)
  return p.toFixed(4)
}

export function humanizeMetricName(name: string): string {
  return name
    .split('_')
    .join(' ')
    .replace(/\busd\b/, '(USD)')
    .replace(/\bms\b/, '(ms)')
    .replace(/^./, (c) => c.toUpperCase())
}

export function humanizeSegmentLabel(label: string): string {
  return label
    .split(' & ')
    .map((clause) => {
      const [dim, val] = clause.split('=')
      return `${dim.split('_').join(' ')}: ${val}`
    })
    .join(' + ')
}

// Pinned to en-US rather than the viewer's OS locale: this is a portfolio
// demo meant to read consistently regardless of who's viewing it.
export function formatDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
