import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOnboardingStatus, useProjectConfig, useSaveProjectConfig } from '../../api/hooks'
import type { OnboardingStatus, ProjectConfigPatch } from '../../api/types'
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
  { id: 'project', labelKey: 'onboarding.steps.project', optional: false },
  { id: 'data', labelKey: 'onboarding.steps.data', optional: false },
  { id: 'metrics', labelKey: 'onboarding.steps.metrics', optional: false },
  { id: 'guardrails', labelKey: 'onboarding.steps.guardrails', optional: false },
  { id: 'segments', labelKey: 'onboarding.steps.segments', optional: false },
  { id: 'economics', labelKey: 'onboarding.steps.economics', optional: false },
  // Stage 15/StatusPanel's own readiness categorization already treats
  // monitoring + notifications as optional polish, never blocking --
  // reflected here rather than re-decided.
  { id: 'monitoring', labelKey: 'onboarding.steps.monitoring', optional: true },
  { id: 'review', labelKey: 'onboarding.steps.review', optional: false },
] as const

/** A visited step only earns the done/✓ marker when it also satisfies
 * its OWN readiness requirement (for the three steps that have one) --
 * otherwise "Metrics" could show done while StatusPanel is still
 * reporting "no primary metric is set" for the exact same step, which
 * reads as directly contradictory. Steps with no specific requirement
 * (project selection itself, segments, economics, review) fall back to
 * "visited", same as before. */
function isStepDone(stepId: (typeof STEPS)[number]['id'], visited: boolean, status: OnboardingStatus | undefined): boolean {
  if (!visited) return false
  if (!status) return true
  if (stepId === 'data') return status.ingestion_connected && status.data_received
  if (stepId === 'metrics') return status.primary_metric_configured
  if (stepId === 'guardrails') return status.guardrails_configured
  return true
}

/** Stage 15: guides a new team through configuring a project end to end
 * without ever touching JSON, Python, or the API directly -- every step
 * reads and writes through the same persisted project-config API the
 * rest of the platform already uses (no second configuration system).
 * Steps past "Project & domain" require an active project to operate on. */
export function OnboardingPage() {
  const { t } = useTranslation()
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
      return <div className="state-box">{t('onboarding.page.selectProjectFirst')}</div>
    }
    if (stepId === 'data') return <DataSourceStep status={statusQuery.data} isLoading={statusQuery.isLoading} />
    // Stage 17 task 4: a failed config request must not render
    // identically to "still loading" forever -- the two are actionable
    // very differently (wait vs. retry/report).
    if (configQuery.error) return <ErrorState error={configQuery.error} />
    if (!config) return <div className="state-box">{t('onboarding.page.loadingConfig')}</div>
    if (stepId === 'metrics') return <MetricsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'guardrails') return <GuardrailsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'segments') return <SegmentsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'economics') return <EconomicsStep config={config} onSave={handleSave} saving={saveMutation.isPending} />
    if (stepId === 'monitoring') return <MonitoringStep domain={domain} projectId={activeProjectId} config={config} onSave={handleSave} saving={saveMutation.isPending} />
    return <ReviewStep config={config} />
  }

  const currentIndex = STEPS.findIndex((s) => s.id === stepId)

  return (
    <div className="page">
      <div className="page-hero">
        <div className="deco deco-blob" aria-hidden="true" style={{ width: 150, height: 150, top: -60, right: -30, background: 'var(--color-lime)', opacity: 0.5 }} />
        <div className="page-hero-content">
          <h1>{t('onboarding.page.title')}</h1>
          <p className="text-secondary" style={{ marginBottom: 14 }}>{t('onboarding.page.subtitle')}</p>
          <div role="progressbar" aria-valuenow={currentIndex + 1} aria-valuemin={1} aria-valuemax={STEPS.length} aria-label={t('onboarding.page.progressLabel')} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ flex: 1, maxWidth: 320, height: 6, borderRadius: 999, background: 'var(--color-border)', overflow: 'hidden' }}>
              <div style={{ height: '100%', borderRadius: 999, background: 'linear-gradient(90deg, var(--color-accent), var(--color-cyan))', width: `${((currentIndex + 1) / STEPS.length) * 100}%`, transition: 'width 0.2s ease' }} />
            </div>
            <span className="text-muted" style={{ fontSize: 12, fontWeight: 600 }}>{t('onboarding.page.stepOf', { current: currentIndex + 1, total: STEPS.length })}</span>
          </div>
        </div>
      </div>

      {hasProject && <StatusPanel status={statusQuery.data} isLoading={statusQuery.isLoading} />}

      <div className="onboarding-layout">
        <nav className="stepper" aria-label="Setup steps">
          {STEPS.map((step, index) => {
            const done = isStepDone(step.id, index < currentIndex, statusQuery.data)
            return (
              <button
                key={step.id}
                type="button"
                className={`step-item${step.id === stepId ? ' active' : ''}`}
                onClick={() => setStepId(step.id)}
              >
                <span className={`step-marker${done ? ' done' : ''}`} aria-hidden="true">{done ? '✓' : index + 1}</span>
                {t(step.labelKey)}
                {step.optional && <span className="text-muted" aria-hidden="true" style={{ fontSize: 10.5, fontWeight: 500 }}>{t('onboarding.page.optionalLabel')}</span>}
              </button>
            )
          })}
        </nav>
        <div>{renderStep()}</div>
      </div>
    </div>
  )
}
