import { useTranslation } from 'react-i18next'
import type { OnboardingStatus } from '../../api/types'

/** Stage 15 task 1: read-only data-source status, sourced entirely from
 * the existing onboarding-status endpoint -- no new connector-setup UI
 * here (out of scope for this stage), just a plain-language explanation
 * of how data gets in and whether any has arrived yet. */
export function DataSourceStep({ status, isLoading }: { status: OnboardingStatus | undefined; isLoading: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="card">
      <div className="card-header">
        <h2>{t('onboarding.steps.data')}</h2>
        <p>{t('onboarding.dataSource.subtitle')}</p>
      </div>

      {isLoading ? (
        <div className="state-box">{t('onboarding.dataSource.checking')}</div>
      ) : status ? (
        <div className="grid-2">
          <div className="card" style={{ boxShadow: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{t('onboarding.dataSource.ingestionConnected')}</strong>
              <span className={`chip ${status.ingestion_connected ? 'chip-positive' : 'chip-negative'}`}>
                {status.ingestion_connected ? t('common.yes') : t('common.no')}
              </span>
            </div>
            <p className="text-secondary" style={{ marginTop: 8, fontSize: 12.5 }}>
              {t('onboarding.dataSource.ingestionDescription')}
            </p>
          </div>
          <div className="card" style={{ boxShadow: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{t('onboarding.dataSource.sessionsReceived')}</strong>
              <span className={`chip ${status.data_received ? 'chip-positive' : 'chip-warning'}`}>
                {status.data_received ? t('common.yes') : t('onboarding.dataSource.notYet')}
              </span>
            </div>
            <p className="text-secondary" style={{ marginTop: 8, fontSize: 12.5 }}>
              {status.data_received
                ? t('onboarding.dataSource.sessionsReceivedDescription')
                : t('onboarding.dataSource.noSessionsDescription')}
            </p>
          </div>
        </div>
      ) : (
        <div className="state-box">{t('onboarding.dataSource.selectProject')}</div>
      )}
    </div>
  )
}
