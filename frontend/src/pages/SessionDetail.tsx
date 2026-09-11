import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useClassifierEvaluation, useDomainSessionDetail } from '../api/hooks'
import { EmptyState, ErrorState, LoadingState } from '../components/common/States'
import { MockClassifierBanner } from '../components/common/MockClassifierBanner'
import { useActiveProject } from '../state/ActiveProjectContext'

const OUTCOME_CHIP: Record<string, string> = {
  resolved: 'chip-positive',
  converted: 'chip-positive',
  purchase: 'chip-positive',
  abandoned: 'chip-negative',
  escalated: 'chip-negative',
}

/** Stage 16: domain-generic (previously called the legacy, unscoped
 * /sessions/{id} endpoint). The old commerce-only session detail carried
 * rich per-session fields (requested_category, platform, cost, token
 * counts, product recommendations, product events, per-message latency)
 * with no generic equivalent -- the generic ingestion schema only
 * guarantees a transcript, an action sequence, tool calls, and an
 * outcome. This screen shows exactly that, plus failure attributions;
 * "Show raw / technical detail" still exposes the full JSON response for
 * anything domain-specific ingested beyond the generic shape. */
export function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [showRaw, setShowRaw] = useState(false)
  const { activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const projectId = activeProject?.project_id
  const { data: session, isLoading, error } = useDomainSessionDetail(domain, projectId, sessionId)
  const { data: classifierEval } = useClassifierEvaluation()

  if (isLoading) return <div className="page"><LoadingState label="Loading session…" /></div>
  if (error) return <div className="page"><ErrorState error={error} /></div>
  if (!session) return <div className="page"><EmptyState>Session not found.</EmptyState></div>

  return (
    <div className="page">
      <div>
        <Link to="/sessions" className="text-secondary" style={{ fontSize: 12.5 }}>← Back to sessions</Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
          <h1>Session {session.session_id.slice(0, 8)}…</h1>
          <span className={`chip ${OUTCOME_CHIP[session.outcome] ?? 'chip-neutral'}`}>{session.outcome.replace(/_/g, ' ')}</span>
          <span className="chip chip-neutral">{session.domain}</span>
        </div>
      </div>

      {session.failure_attributions.length > 0 && (
        <>
          {classifierEval && <MockClassifierBanner provenance={classifierEval.provenance} />}
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
                  {f.review_status !== 'unreviewed' && (
                    <span className={`chip ${f.review_status === 'confirmed' ? 'chip-positive' : 'chip-negative'}`} style={{ fontSize: 10.5 }}>
                      {f.review_status}
                    </span>
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
          <p>User/agent transcript, action sequence, and tool calls for this session — no chain-of-thought.</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {session.transcript.map(([sender, text], i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
              <span className="chip chip-neutral" style={{ minWidth: 56, textAlign: 'center', flexShrink: 0 }}>{sender}</span>
              <span style={{ fontSize: 13 }}>{text}</span>
            </div>
          ))}
          {session.transcript.length === 0 && <EmptyState>No transcript recorded for this session.</EmptyState>}
        </div>

        {session.action_sequence.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              Action sequence
            </div>
            <div className="mono" style={{ fontSize: 12.5 }}>{session.action_sequence.join(' → ')}</div>
          </div>
        )}

        {session.tool_calls.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="text-muted" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
              Tool calls
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>Tool</th><th>Success</th><th>Error</th></tr></thead>
                <tbody>
                  {session.tool_calls.map((tc, i) => (
                    <tr key={i}>
                      <td>{tc.tool_name}</td>
                      <td>{tc.success ? 'yes' : 'no'}</td>
                      <td className="text-muted">{tc.error_type === 'none' ? '—' : tc.error_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
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
