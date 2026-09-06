import type { AgentAction, MessageItem, ProductEvent, ToolCall } from '../../api/types'
import { formatDateTime } from '../../lib/format'

type TimelineRow =
  | { kind: 'message'; time: string; message: MessageItem }
  | { kind: 'action'; time: string; action: AgentAction; toolCalls: ToolCall[] }
  | { kind: 'product_event'; time: string; event: ProductEvent }

const KIND_STYLE: Record<string, { border: string; bg: string; label: string }> = {
  user: { border: 'var(--color-accent)', bg: 'var(--color-accent-weak)', label: 'User' },
  agent: { border: 'var(--color-text-secondary)', bg: 'var(--color-neutral-weak)', label: 'Agent' },
  action: { border: 'var(--color-warning)', bg: 'var(--color-warning-weak)', label: 'Action / tool' },
  product_event: { border: 'var(--color-positive)', bg: 'var(--color-positive-weak)', label: 'Product event' },
}

/** Merges messages, agent actions (with their nested tool calls), and
 * product events into one true chronological timeline, using the real
 * timestamps each already carries (messages.created_at,
 * agent_actions.started_at, product_events.event_time) — not an inferred
 * or approximated ordering. Only observable traces are shown; no
 * chain-of-thought (Stage 6 SS7). */
export function SessionTimeline({
  messages, actions, toolCalls, productEvents,
}: {
  messages: MessageItem[]
  actions: AgentAction[]
  toolCalls: ToolCall[]
  productEvents: ProductEvent[]
}) {
  const toolCallsByAction = new Map<number, ToolCall[]>()
  for (const tc of toolCalls) {
    const list = toolCallsByAction.get(tc.action_sequence_index) ?? []
    list.push(tc)
    toolCallsByAction.set(tc.action_sequence_index, list)
  }

  const rows: TimelineRow[] = [
    ...messages.map((m): TimelineRow => ({ kind: 'message', time: m.created_at, message: m })),
    ...actions.map((a): TimelineRow => ({ kind: 'action', time: a.started_at, action: a, toolCalls: toolCallsByAction.get(a.sequence_index) ?? [] })),
    ...productEvents.map((e): TimelineRow => ({ kind: 'product_event', time: e.event_time, event: e })),
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())

  if (rows.length === 0) {
    return <p className="text-muted" style={{ fontSize: 12.5 }}>No timeline events recorded for this session.</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {rows.map((row, i) => {
        if (row.kind === 'message') {
          const style = KIND_STYLE[row.message.sender] ?? KIND_STYLE.agent
          return (
            <div key={`m-${i}`} style={{ borderLeft: `3px solid ${style.border}`, background: style.bg, borderRadius: 4, padding: '8px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                <strong>{style.label}</strong>
                <span className="text-muted mono">{formatDateTime(row.message.created_at)}</span>
              </div>
              <div style={{ fontSize: 13 }}>{row.message.text}</div>
              <div className="text-muted" style={{ fontSize: 10.5, marginTop: 3 }}>
                {row.message.tokens} tokens{row.message.latency_ms !== null ? ` · ${row.message.latency_ms}ms` : ''}
              </div>
            </div>
          )
        }
        if (row.kind === 'action') {
          const style = KIND_STYLE.action
          return (
            <div key={`a-${i}`} style={{ borderLeft: `3px solid ${style.border}`, background: style.bg, borderRadius: 4, padding: '8px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                <strong>{style.label}: {row.action.action_type.replace(/_/g, ' ')}</strong>
                <span className="text-muted mono">{formatDateTime(row.action.started_at)}</span>
              </div>
              <div className="text-muted" style={{ fontSize: 10.5 }}>
                {row.action.model_name} · {row.action.latency_ms}ms
              </div>
              {row.toolCalls.length > 0 && (
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {row.toolCalls.map((tc, j) => (
                    <div key={j} style={{ fontSize: 11.5, display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="mono">{tc.tool_name}</span>
                      <span className={`chip ${tc.success ? 'chip-positive' : 'chip-negative'}`} style={{ fontSize: 10 }}>
                        {tc.success ? 'success' : tc.error_type}
                      </span>
                      <span className="text-muted">{tc.latency_ms}ms</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        }
        const style = KIND_STYLE.product_event
        return (
          <div key={`e-${i}`} style={{ borderLeft: `3px solid ${style.border}`, background: style.bg, borderRadius: 4, padding: '8px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <strong>{style.label}: {row.event.event_type}</strong>
              <span className="text-muted mono">{formatDateTime(row.event.event_time)}</span>
            </div>
            <div className="text-muted" style={{ fontSize: 10.5, marginTop: 3 }}>price at event: ${(row.event.price_at_event / 100).toFixed(2)}</div>
          </div>
        )
      })}
    </div>
  )
}
