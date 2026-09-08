import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSessionDetail } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { SessionTimeline } from '../components/session/SessionTimeline'
import { formatDateTime } from '../lib/format'

const OUTCOME_CHIP: Record<string, string> = {
  purchase: 'chip-positive',
  add_to_cart_only: 'chip-neutral',
  no_action: 'chip-neutral',
  abandoned: 'chip-negative',
}

export function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [showRaw, setShowRaw] = useState(false)
  const { data: session, isLoading, error } = useSessionDetail(sessionId)

  if (isLoading) return <div className="page"><LoadingState label="Loading session…" /></div>
  if (error) return <div className="page"><ErrorState message={(error as Error).message} /></div>
  if (!session) return <div className="page"><EmptyState>Session not found.</EmptyState></div>

  return (
    <div className="page">
      <div>
        <Link to="/sessions" className="text-secondary" style={{ fontSize: 12.5 }}>← Back to sessions</Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
          <h1>Session {session.session_id.slice(0, 8)}…</h1>
          <span className={`chip ${OUTCOME_CHIP[session.outcome] ?? 'chip-neutral'}`}>{session.outcome.replace(/_/g, ' ')}</span>
          <span className="chip chip-neutral">{session.agent_version}</span>
        </div>
      </div>

      <div className="card">
        <div className="grid-3">
          <div><div className="text-muted" style={{ fontSize: 11 }}>Category</div><div>{session.requested_category} · {session.constraint_count_bucket} constraints ({session.num_constraints})</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Platform / device</div><div>{session.platform} · {session.device_tier} tier</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Locale / persona</div><div>{session.locale} · {session.persona}</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Turns</div><div>{session.num_turns}</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Total latency</div><div>{session.total_latency_ms.toLocaleString('en-US')}ms</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Total cost</div><div>${session.total_cost_usd.toFixed(4)}</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Started</div><div>{formatDateTime(session.started_at)}</div></div>
          <div><div className="text-muted" style={{ fontSize: 11 }}>Ended</div><div>{session.ended_at ? formatDateTime(session.ended_at) : '—'}</div></div>
        </div>
      </div>

      {session.failure_attributions.length > 0 && (
        <>
          <MockClassifierBanner provenance={session.failure_attributions[0].provenance} />
          <div className="card">
            <div className="card-header"><h2>Detected failure mechanisms</h2><p>A session can have zero, one, or several — mechanisms are not mutually exclusive.</p></div>
            {session.failure_attributions.map((f) => (
              <div key={f.failure_mode} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 4 }}>
                  <span className="chip chip-warning">{f.failure_mode.replace(/_/g, ' ')}</span>
                  <span className="text-muted" style={{ fontSize: 12 }}>source: {f.detector_source.replace(/_/g, ' ')}</span>
                  {f.confidence !== null && (
                    <span className="text-muted" style={{ fontSize: 12 }}>confidence {(f.confidence * 100).toFixed(0)}%</span>
                  )}
                </div>
                {f.evidence_text && <p style={{ fontSize: 13 }}>{f.evidence_text}</p>}
              </div>
            ))}
          </div>
        </>
      )}

      <div className="card">
        <div className="card-header">
          <h2>Timeline</h2>
          <p>User, agent, tool/action, and product events in true chronological order — no chain-of-thought.</p>
        </div>
        <SessionTimeline
          messages={session.transcript}
          actions={session.agent_actions}
          toolCalls={session.tool_calls}
          productEvents={session.product_events}
        />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><h2>Recommendations shown</h2></div>
          {session.recommendations.length === 0 && <EmptyState>No recommendations were shown.</EmptyState>}
          {session.recommendations.length > 0 && (
            <table className="data-table">
              <thead><tr><th>Rank</th><th>Product</th><th>Clicked</th><th>Satisfies constraints</th></tr></thead>
              <tbody>
                {session.recommendations.map((r) => (
                  <tr key={r.product_id}>
                    <td>{r.rank_position}</td>
                    <td className="mono">{r.product_id.slice(0, 8)}…</td>
                    <td>{r.clicked ? 'yes' : 'no'}</td>
                    <td>{r.satisfies_constraints ? 'yes' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <div className="card-header"><h2>Deterministic evaluation signals</h2></div>
          {session.evaluations.length === 0 && <EmptyState>No evaluations recorded.</EmptyState>}
          {session.evaluations.length > 0 && (
            <table className="data-table">
              <thead><tr><th>Eval type</th><th>Score</th><th>Evaluator</th></tr></thead>
              <tbody>
                {session.evaluations.map((e) => (
                  <tr key={e.eval_type}><td>{e.eval_type.replace(/_/g, ' ')}</td><td className="mono">{e.score.toFixed(2)}</td><td className="text-muted">{e.evaluator}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card">
        <button type="button" className="btn btn-small" onClick={() => setShowRaw((v) => !v)} aria-expanded={showRaw}>
          {showRaw ? 'Hide' : 'Show'} raw / technical detail
        </button>
        {showRaw && (
          <pre className="mono" style={{ marginTop: 12, fontSize: 11, whiteSpace: 'pre-wrap', overflowX: 'auto' }}>
{JSON.stringify(session, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
