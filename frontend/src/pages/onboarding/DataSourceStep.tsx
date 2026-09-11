import type { OnboardingStatus } from '../../api/types'

/** Stage 15 task 1: read-only data-source status, sourced entirely from
 * the existing onboarding-status endpoint -- no new connector-setup UI
 * here (out of scope for this stage), just a plain-language explanation
 * of how data gets in and whether any has arrived yet. */
export function DataSourceStep({ status, isLoading }: { status: OnboardingStatus | undefined; isLoading: boolean }) {
  return (
    <div className="card">
      <div className="card-header">
        <h2>Data source</h2>
        <p>Where this project's session data comes from, and whether it's flowing.</p>
      </div>

      {isLoading ? (
        <div className="state-box">Checking data source…</div>
      ) : status ? (
        <div className="grid-2">
          <div className="card" style={{ boxShadow: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Ingestion connected</strong>
              <span className={`chip ${status.ingestion_connected ? 'chip-positive' : 'chip-negative'}`}>
                {status.ingestion_connected ? 'Yes' : 'No'}
              </span>
            </div>
            <p className="text-secondary" style={{ marginTop: 8, fontSize: 12.5 }}>
              This project can accept session data. New sessions can be sent to the ingestion API directly, imported from
              Langfuse traces, or enriched from a Postgres business database -- whichever fits your stack.
            </p>
          </div>
          <div className="card" style={{ boxShadow: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Sessions received</strong>
              <span className={`chip ${status.data_received ? 'chip-positive' : 'chip-warning'}`}>
                {status.data_received ? 'Yes' : 'Not yet'}
              </span>
            </div>
            <p className="text-secondary" style={{ marginTop: 8, fontSize: 12.5 }}>
              {status.data_received
                ? 'At least one session has been recorded for this project.'
                : 'No sessions have arrived yet. Metrics, guardrails, and release decisions all depend on real session data being ingested first.'}
            </p>
          </div>
        </div>
      ) : (
        <div className="state-box">Select a project to see its data-source status.</div>
      )}
    </div>
  )
}
