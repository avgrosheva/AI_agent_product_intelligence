import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { ProjectConfig } from '../../api/types'

export function ReviewStep({ config }: { config: ProjectConfig }) {
  const { t } = useTranslation()
  return (
    <div className="card">
      <div className="card-header">
        <h2>{t('onboarding.steps.review')}</h2>
        <p>{t('onboarding.review.subtitle')}</p>
      </div>
      <table className="data-table">
        <tbody>
          <tr><td>{t('onboarding.review.primaryMetric')}</td><td className="mono">{config.primary_metric ?? t('onboarding.review.notSet')}</td></tr>
          <tr><td>{t('onboarding.review.metrics')}</td><td>{config.metrics === null ? t('onboarding.review.domainDefaults') : t('onboarding.review.customMetrics', { count: config.metrics.metrics.length })}</td></tr>
          <tr><td>{t('onboarding.review.guardrails')}</td><td>{t('onboarding.review.active', { count: config.available_guardrails.length })}</td></tr>
          <tr><td>{t('onboarding.review.segments')}</td><td>{config.segment_dimensions ? Object.keys(config.segment_dimensions).join(', ') : t('onboarding.review.noneSelected')}</td></tr>
          <tr><td>{t('onboarding.review.economics')}</td><td>{config.economics ? t('onboarding.review.mapped') : t('onboarding.review.notMapped')}</td></tr>
          <tr><td>{t('onboarding.review.notificationEvents')}</td><td>{config.enabled_notification_rules.length > 0 ? config.enabled_notification_rules.join(', ') : t('onboarding.review.noneEnabled')}</td></tr>
        </tbody>
      </table>
      <Link to="/project" className="btn btn-primary" style={{ marginTop: 16, alignSelf: 'flex-start' }}>
        {t('onboarding.review.goToProjectOverview')}
      </Link>
    </div>
  )
}
