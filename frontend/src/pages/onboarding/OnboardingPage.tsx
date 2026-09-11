import { useState } from 'react'
import { useOnboardingStatus, useProjectConfig, useSaveProjectConfig } from '../../api/hooks'
import type { ProjectConfigPatch } from '../../api/types'
import { ErrorState } from '../../components/common/States'
import { useActiveProject } from '../../state/ActiveProjectContext'
import { DataSourceStep } from './DataSourceStep'
import { EconomicsStep } from './EconomicsStep'
import { GuardrailsStep } from './GuardrailsStep'
import { MetricsStep } from './MetricsStep'
import { MonitoringStep } from './MonitoringStep'
import { ProjectStep } from './ProjectStep'
import { ReviewStep } from './ReviewStep'
import { SegmentsStep } from './SegmentsStep'
import { StatusPanel } from './StatusPanel'

const STEPS = [
  { id: 'project', label: 'Project & domain' },
  { id: 'data', label: 'Data source' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'guardrails', label: 'Guardrails' },
  { id: 'segments', label: 'Segments' },
  { id: 'economics', label: 'Economics' },
  { id: 'monitoring', label: 'Monitoring & notifications' },
  { id: 'review', label: 'Review' },
] as const

/** Stage 15: guides a new team through configuring a project end to end
 * without ever touching JSON, Python, or the API directly -- every step
 * reads and writes through the same persisted project-config API the
 * rest of the platform already uses (no second configuration system).
 * Steps past "Project & domain" require an active project to operate on. */
export function OnboardingPage() {
  const { activeProject, activeProjectId } = useActiveProject()
  const domain = activeProject?.domain
  const [stepId, setStepId] = useState<(typeof STEPS)[number]['id']>('project')

  const configQuery = useProjectConfig(domain, activeProjectId ?? undefined)
  const statusQuery = useOnboardingStatus(domain, activeProjectId ?? undefined)
  const saveMutation = useSaveProjectConfig(domain, activeProjectId ?? undefined)

  async function handleSave(patch: ProjectConfigPatch) {
    const current = configQuery.data
    if (!current) return
    const fullBody: ProjectConfigPatch = {
      primary_metric: current.primary_metric,
      metrics: current.metrics,
      guardrails: current.guardrails,
      segment_dimensions: current.segment_dimensions,
      economics: current.economics,
      monitoring_cadence_seconds: current.monitoring_cadence_seconds,
      enabled_notification_rules: current.enabled_notification_rules,
      ...patch,
    }
    return saveMutation.mutateAsync(fullBody)
  }

  const hasProject = !!activeProjectId && !!domain
  const config = configQuery.data

  function renderStep() {
    if (stepId === 'project') return <ProjectStep />
    if (!hasProject) {
      return <div className="state-box">Select or create a project in the "Project &amp; domain" step first.</div>
    }
    if (stepId === 'data') return <DataSourceStep status={statusQuery.data} isLoading={statusQuery.isLoading} />
    // Stage 17 task 4: a failed config request must not render
    // identically to "still loading" forever -- the two are actionable
    // very differently (wait vs. retry/report).
    if (configQuery.error) return <ErrorState error={configQuery.error} />
    if (!config) return <div className="state-box">Loading configuration…</div>
    if (stepId === 'metrics') return <MetricsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'guardrails') return <GuardrailsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'segments') return <SegmentsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'economics') return <EconomicsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'monitoring') return <MonitoringStep domain={domain} projectId={activeProjectId} config={config} onSave={handleSave} saving={saveMutation.isPending} />
    return <ReviewStep config={config} />
  }

  return (
    <div className="page">
      <div>
        <h1>Project setup</h1>
        <p className="text-secondary">Configure this project's metrics, guardrails, segments, and monitoring -- no JSON or API calls required.</p>
      </div>

      {hasProject && <StatusPanel status={statusQuery.data} isLoading={statusQuery.isLoading} />}

      <div className="onboarding-layout">
        <nav className="stepper" aria-label="Setup steps">
          {STEPS.map((step, index) => (
            <button
              key={step.id}
              type="button"
              className={`step-item${step.id === stepId ? ' active' : ''}`}
              onClick={() => setStepId(step.id)}
            >
              <span className="step-marker" aria-hidden="true">{index + 1}</span>
              {step.label}
            </button>
          ))}
        </nav>
        <div>{renderStep()}</div>
      </div>
    </div>
  )
}
