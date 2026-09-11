import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useCreateMonitoringConfig,
  useCreateNotificationChannel,
  useGenericExperiments,
  useMonitoringConfigs,
  useNotificationChannels,
} from '../../api/hooks'
import type { ProjectConfig, ProjectConfigPatch } from '../../api/types'
import { humanizeMetricName } from '../../lib/format'
import { formatValidationErrors } from './validationError'

// Mirrors backend.project_config.service.VALID_EVENT_TYPES -- a small,
// stable vocabulary not worth a round trip to expose dynamically.
const EVENT_TYPES = [
  { value: 'ROLLBACK', labelKey: 'onboarding.monitoring.eventRollback' },
  { value: 'HOLD', labelKey: 'onboarding.monitoring.eventHold' },
  { value: 'BLOCKING_GUARDRAIL_BREACH', labelKey: 'onboarding.monitoring.eventBlockingGuardrail' },
  { value: 'CRITICAL_DATA_QUALITY', labelKey: 'onboarding.monitoring.eventCriticalDataQuality' },
  { value: 'MONITORING_JOB_FAILURE', labelKey: 'onboarding.monitoring.eventMonitoringFailure' },
]

interface Props {
  domain: string
  projectId: string
  config: ProjectConfig
  onSave: (patch: ProjectConfigPatch) => Promise<unknown>
  saving: boolean
}

export function MonitoringStep({ domain, projectId, config, onSave, saving }: Props) {
  const { t } = useTranslation()
  const experimentsQuery = useGenericExperiments(domain, projectId)
  const monitoringQuery = useMonitoringConfigs(domain, projectId)
  const createMonitoring = useCreateMonitoringConfig(domain, projectId)
  const channelsQuery = useNotificationChannels(domain, projectId)
  const createChannel = useCreateNotificationChannel(domain, projectId)

  const experiments = experimentsQuery.data?.experiments ?? []
  const inferentialMetrics = config.available_metrics.filter((m) => m.is_inferential)

  const [showMonitoringForm, setShowMonitoringForm] = useState(false)
  const [experimentId, setExperimentId] = useState('')
  const [primaryMetric, setPrimaryMetric] = useState('')
  const [cadenceSeconds, setCadenceSeconds] = useState(3600)
  const [windowHours, setWindowHours] = useState(24)
  const [monitoringEnabled, setMonitoringEnabled] = useState(true)
  const [monitoringError, setMonitoringError] = useState<string[] | null>(null)

  useEffect(() => {
    if (!experimentId && experiments.length > 0) setExperimentId(experiments[0].experiment_id)
  }, [experiments, experimentId])
  useEffect(() => {
    if (!primaryMetric && inferentialMetrics.length > 0) setPrimaryMetric(inferentialMetrics[0].name)
  }, [inferentialMetrics, primaryMetric])

  const [rules, setRules] = useState<Set<string>>(new Set(config.enabled_notification_rules))
  const [rulesError, setRulesError] = useState<string[] | null>(null)

  const [showChannelForm, setShowChannelForm] = useState(false)
  const [channelType, setChannelType] = useState<'webhook' | 'slack_webhook'>('webhook')
  const [channelUrl, setChannelUrl] = useState('')
  const [channelEnabled, setChannelEnabled] = useState(true)
  const [channelError, setChannelError] = useState<string[] | null>(null)

  async function handleAddMonitoring(e: FormEvent) {
    e.preventDefault()
    setMonitoringError(null)
    try {
      await createMonitoring.mutateAsync({ experiment_id: experimentId, primary_metric: primaryMetric, cadence_seconds: cadenceSeconds, window_hours: windowHours, enabled: monitoringEnabled })
      setShowMonitoringForm(false)
    } catch (err) {
      setMonitoringError(formatValidationErrors(err))
    }
  }

  function toggleRule(rule: string) {
    setRules((prev) => {
      const next = new Set(prev)
      if (next.has(rule)) next.delete(rule)
      else next.add(rule)
      return next
    })
  }

  async function handleSaveRules() {
    setRulesError(null)
    try {
      await onSave({ enabled_notification_rules: Array.from(rules) })
    } catch (err) {
      setRulesError(formatValidationErrors(err))
    }
  }

  async function handleAddChannel(e: FormEvent) {
    e.preventDefault()
    setChannelError(null)
    try {
      await createChannel.mutateAsync({ channel_type: channelType, url: channelUrl, enabled: channelEnabled })
      setChannelUrl('')
      setShowChannelForm(false)
    } catch (err) {
      setChannelError(formatValidationErrors(err))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="card">
        <div className="card-header">
          <h2>{t('onboarding.monitoring.schedulingTitle')}</h2>
          <p>{t('onboarding.monitoring.schedulingSubtitle')}</p>
        </div>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>{t('onboarding.monitoring.colExperiment')}</th><th>{t('onboarding.monitoring.colPrimaryMetric')}</th><th>{t('onboarding.monitoring.colCadence')}</th><th>{t('onboarding.monitoring.colWindow')}</th><th>{t('onboarding.monitoring.colStatus')}</th></tr>
            </thead>
            <tbody>
              {(monitoringQuery.data?.configs ?? []).map((c) => (
                <tr key={c.config_id}>
                  <td>{experiments.find((e) => e.experiment_id === c.experiment_id)?.name ?? c.experiment_id}</td>
                  <td className="mono">{c.primary_metric}</td>
                  <td>{c.cadence_seconds}s</td>
                  <td>{c.window_hours ? `${c.window_hours}h` : t('onboarding.monitoring.fullHistory')}</td>
                  <td><span className={`chip ${c.enabled ? 'chip-positive' : 'chip-neutral'}`}>{c.enabled ? t('onboarding.monitoring.enabled') : t('onboarding.monitoring.disabled')}</span></td>
                </tr>
              ))}
              {(monitoringQuery.data?.configs ?? []).length === 0 && (
                <tr><td colSpan={5} className="text-muted">{t('onboarding.monitoring.noneScheduled')}</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!showMonitoringForm && experiments.length > 0 && (
          <button type="button" className="btn btn-small" style={{ marginTop: 14 }} onClick={() => setShowMonitoringForm(true)}>{t('onboarding.monitoring.scheduleBtn')}</button>
        )}
        {experiments.length === 0 && <p className="text-muted" style={{ fontSize: 12.5, marginTop: 12 }}>{t('onboarding.monitoring.noExperiments')}</p>}

        {showMonitoringForm && (
          <form onSubmit={handleAddMonitoring} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14, borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
            <div className="grid-2">
              <label className="field">
                <span>{t('onboarding.monitoring.colExperiment')}</span>
                <select value={experimentId} onChange={(e) => setExperimentId(e.target.value)}>
                  {experiments.map((e) => <option key={e.experiment_id} value={e.experiment_id}>{e.name}</option>)}
                </select>
              </label>
              <label className="field">
                <span>{t('onboarding.monitoring.colPrimaryMetric')}</span>
                <select value={primaryMetric} onChange={(e) => setPrimaryMetric(e.target.value)}>
                  {inferentialMetrics.map((m) => <option key={m.name} value={m.name}>{m.label || humanizeMetricName(m.name)}</option>)}
                </select>
              </label>
              <label className="field">
                <span>{t('onboarding.monitoring.cadenceSeconds')}</span>
                <input type="number" min={1} value={cadenceSeconds} onChange={(e) => setCadenceSeconds(Number(e.target.value))} />
              </label>
              <label className="field">
                <span>{t('onboarding.monitoring.windowHours')}</span>
                <input type="number" min={1} value={windowHours} onChange={(e) => setWindowHours(Number(e.target.value))} />
              </label>
            </div>
            <label className="checkbox-field">
              <input type="checkbox" checked={monitoringEnabled} onChange={(e) => setMonitoringEnabled(e.target.checked)} />
              {t('onboarding.monitoring.enabled')}
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary" disabled={createMonitoring.isPending}>{createMonitoring.isPending ? t('common.saving') : t('onboarding.monitoring.schedule')}</button>
              <button type="button" className="btn" onClick={() => setShowMonitoringForm(false)}>{t('common.cancel')}</button>
            </div>
          </form>
        )}
        {monitoringError && <div className="chip chip-negative" style={{ marginTop: 12 }}>{monitoringError.join('; ')}</div>}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('onboarding.monitoring.notificationEventsTitle')}</h2>
          <p>{t('onboarding.monitoring.notificationEventsSubtitle')}</p>
        </div>
        <div className="inline-list">
          {EVENT_TYPES.map((et) => (
            <label key={et.value} className="checkbox-field">
              <input type="checkbox" checked={rules.has(et.value)} onChange={() => toggleRule(et.value)} />
              {t(et.labelKey)}
            </label>
          ))}
        </div>
        <button type="button" className="btn btn-primary" style={{ marginTop: 14, alignSelf: 'flex-start' }} onClick={handleSaveRules} disabled={saving}>
          {saving ? t('common.saving') : t('onboarding.monitoring.saveNotificationEvents')}
        </button>
        {rulesError && <div className="chip chip-negative" style={{ marginTop: 12 }}>{rulesError.join('; ')}</div>}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>{t('onboarding.monitoring.channelsTitle')}</h2>
          <p>{t('onboarding.monitoring.channelsSubtitle')}</p>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>{t('onboarding.monitoring.colType')}</th><th>{t('onboarding.monitoring.colUrl')}</th><th>{t('onboarding.monitoring.colStatus')}</th></tr></thead>
            <tbody>
              {(channelsQuery.data?.channels ?? []).map((c) => (
                <tr key={c.channel_id}>
                  <td>{c.channel_type}</td>
                  <td className="mono">{c.url_preview}</td>
                  <td><span className={`chip ${c.enabled ? 'chip-positive' : 'chip-neutral'}`}>{c.enabled ? t('onboarding.monitoring.enabled') : t('onboarding.monitoring.disabled')}</span></td>
                </tr>
              ))}
              {(channelsQuery.data?.channels ?? []).length === 0 && (
                <tr><td colSpan={3} className="text-muted">{t('onboarding.monitoring.noneChannels')}</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!showChannelForm && (
          <button type="button" className="btn btn-small" style={{ marginTop: 14 }} onClick={() => setShowChannelForm(true)}>{t('onboarding.monitoring.addChannelBtn')}</button>
        )}

        {showChannelForm && (
          <form onSubmit={handleAddChannel} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 14, borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
            <div className="grid-2">
              <label className="field">
                <span>{t('onboarding.monitoring.colType')}</span>
                <select value={channelType} onChange={(e) => setChannelType(e.target.value as 'webhook' | 'slack_webhook')}>
                  <option value="webhook">{t('onboarding.monitoring.webhook')}</option>
                  <option value="slack_webhook">{t('onboarding.monitoring.slackWebhook')}</option>
                </select>
              </label>
              <label className="field">
                <span>{t('onboarding.monitoring.colUrl')}</span>
                <input value={channelUrl} onChange={(e) => setChannelUrl(e.target.value)} required className="mono" placeholder="https://…" />
              </label>
            </div>
            <label className="checkbox-field">
              <input type="checkbox" checked={channelEnabled} onChange={(e) => setChannelEnabled(e.target.checked)} />
              {t('onboarding.monitoring.enabled')}
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary" disabled={createChannel.isPending}>{createChannel.isPending ? t('common.saving') : t('onboarding.monitoring.addChannel')}</button>
              <button type="button" className="btn" onClick={() => setShowChannelForm(false)}>{t('common.cancel')}</button>
            </div>
          </form>
        )}
        {channelError && <div className="chip chip-negative" style={{ marginTop: 12 }}>{channelError.join('; ')}</div>}
      </div>
    </div>
  )
}
