import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageToggle } from '../common/LanguageToggle'
import { ThemeToggle } from '../common/ThemeToggle'
import { useActiveExperiment } from '../../state/ActiveExperimentContext'
import { useActiveProject } from '../../state/ActiveProjectContext'
import { useAuth } from '../../state/AuthContext'

const STATUS_LABEL_KEY: Record<string, string> = {
  ambiguous_investigate: 'appLayout.statusNeedsInvestigation',
  no_regression_detected: 'appLayout.statusNoRegression',
  not_yet_investigated: 'appLayout.statusNotYetInvestigated',
}

// Routes that manage project selection themselves (ProjectOverview already
// has its own "no project selected" state with a link to /setup; the
// onboarding wizard's first step IS the project picker/creator) -- these
// must stay reachable no matter which project-selection state the rest of
// the shell is in, otherwise a brand-new user with zero projects, or one
// who needs to pick among several, would have no way to get there.
const PROJECT_MANAGEMENT_PATHS = ['/setup', '/project']

function ProjectSwitcher() {
  const { t } = useTranslation()
  const { projects, activeProjectId, setActiveProjectId } = useActiveProject()
  if (projects.length < 2) return null
  return (
    <label className="project-switcher">
      <span className="text-muted">{t('appLayout.project')}</span>
      <select
        value={activeProjectId ?? ''}
        onChange={(e) => setActiveProjectId(e.target.value)}
        aria-label="Switch active project"
      >
        {!activeProjectId && (
          <option value="" disabled>
            {t('appLayout.selectAProjectEllipsis')}
          </option>
        )}
        {projects.map((p) => (
          <option key={p.project_id} value={p.project_id}>
            {p.name} ({p.domain})
          </option>
        ))}
      </select>
    </label>
  )
}

function ProjectPickerPrompt() {
  const { t } = useTranslation()
  const { projects, setActiveProjectId } = useActiveProject()
  return (
    <div className="page">
      <div className="page-hero" style={{ maxWidth: 560, margin: '48px auto', textAlign: 'center' }}>
        <div className="deco deco-blob" aria-hidden="true" style={{ width: 160, height: 160, top: -50, left: -60, background: 'var(--color-lime)' }} />
        {/* Stage 20: kept fully inside the card's own bounds (not
            edge-bleeding like the blob/pixel decorations) -- a rotated
            element positioned to straddle the border here was observed
            escaping the card's overflow:hidden clip in Chromium. */}
        <div className="deco deco-bar" aria-hidden="true" style={{ width: 110, height: 20, top: 18, right: 14, background: 'var(--color-accent)' }} />
        <div className="page-hero-content">
          <h1 style={{ marginBottom: 6 }}>{t('appLayout.selectAProject')}</h1>
          <p className="text-secondary" style={{ marginBottom: 22 }}>{t('appLayout.belongToMultipleProjects')}</p>
          <div className="inline-list">
            {projects.map((p) => (
              <div
                key={p.project_id}
                className="selectable-card"
                onClick={() => setActiveProjectId(p.project_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') setActiveProjectId(p.project_id)
                }}
              >
                <div>
                  <strong>{p.name}</strong>
                  <div className="text-muted" style={{ fontSize: 12 }}>{p.domain}</div>
                </div>
                <span className="chip chip-accent">{t('appLayout.open')}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function NoProjectPrompt() {
  const { t } = useTranslation()
  return (
    <div className="page">
      <div className="page-hero" style={{ maxWidth: 480, margin: '48px auto', textAlign: 'center' }}>
        <div className="deco deco-pixels" aria-hidden="true" style={{ width: 140, height: 140, top: -20, right: -30, color: 'var(--color-lime)' }} />
        <div className="page-hero-content">
          <div className="empty-glyph" />
          <h1 style={{ fontSize: 24, marginBottom: 6 }}>{t('appLayout.noProjectYetTitle')}</h1>
          <p className="text-secondary" style={{ marginBottom: 18 }}>{t('appLayout.noProjectYetBody')}</p>
          <Link to="/setup" className="btn btn-primary">
            {t('appLayout.setUpFirstProject')}
          </Link>
        </div>
      </div>
    </div>
  )
}

export function AppLayout() {
  const { t } = useTranslation()
  const { activeProject, projects, isLoading: projectsLoading, needsExplicitSelection } = useActiveProject()
  const { activeExperimentId, activeExperiment } = useActiveExperiment()
  const { logout } = useAuth()
  const location = useLocation()

  const onProjectManagementRoute = PROJECT_MANAGEMENT_PATHS.some((p) => location.pathname.startsWith(p))
  const showNoProjectPrompt = !onProjectManagementRoute && !projectsLoading && projects.length === 0
  const showPicker = !onProjectManagementRoute && needsExplicitSelection

  // Stage 16 fix: these four screens are meaningless without an active
  // experiment -- previously they stayed live NavLinks built from
  // `${expPath}/...` with expPath defaulted to '/', producing malformed
  // double-slash paths ('//investigation') the moment no experiment was
  // selected yet (e.g. mid project-selection, or a freshly-created
  // project with zero experiments). Rendered as disabled instead of
  // linking somewhere broken.
  const expPath = activeExperimentId ? `/experiments/${activeExperimentId}` : null

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand-mark">
            <span className="brand-glyph" aria-hidden="true" />
            <span className="sidebar-brand">AI Agent<br />Product Intelligence</span>
          </div>
          <div className="sidebar-brand-sub">
            {activeProject ? `${activeProject.name} · ${activeProject.domain}` : projectsLoading ? t('common.loading') : t('appLayout.noProjectSelected')}
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.overview')}
          </NavLink>
          {expPath ? (
            <>
              <NavLink to={expPath} end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                {t('nav.experiment')}
              </NavLink>
              <NavLink to={`${expPath}/release`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                {t('nav.releaseDecision')}
              </NavLink>
              <NavLink to={`${expPath}/investigation`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                {t('nav.investigation')}
              </NavLink>
            </>
          ) : (
            <>
              <span className="sidebar-link sidebar-link-disabled" title={t('nav.selectProjectFirst')} aria-disabled="true">{t('nav.experiment')}</span>
              <span className="sidebar-link sidebar-link-disabled" title={t('nav.selectProjectFirst')} aria-disabled="true">{t('nav.releaseDecision')}</span>
              <span className="sidebar-link sidebar-link-disabled" title={t('nav.selectProjectFirst')} aria-disabled="true">{t('nav.investigation')}</span>
            </>
          )}
          <NavLink to="/sessions" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.sessions')}
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.alerts')}
          </NavLink>
          <NavLink to="/review-queue" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.reviewQueue')}
          </NavLink>
          {expPath ? (
            <NavLink to={`${expPath}/ai-quality`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
              {t('nav.aiQuality')}
            </NavLink>
          ) : (
            <span className="sidebar-link sidebar-link-disabled" title={t('nav.selectProjectFirst')} aria-disabled="true">{t('nav.aiQuality')}</span>
          )}
          <NavLink to="/project" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.projectOverview')}
          </NavLink>
          <NavLink to="/setup" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            {t('nav.projectSetup')}
          </NavLink>
        </nav>
        <ProjectSwitcher />
      </aside>
      <div className="main-area">
        <header className="top-bar">
          <div className="active-experiment">
            <span className="text-muted">{t('appLayout.activeExperiment')}</span>
            {activeExperiment ? (
              <>
                <strong>{activeExperiment.name}</strong>
                <span className="text-muted">({activeExperiment.control_version} vs {activeExperiment.treatment_version})</span>
              </>
            ) : (
              <span className="text-muted">{t('appLayout.noneSelected')}</span>
            )}
          </div>
          {activeExperiment && (
            <span className={`chip ${activeExperiment.status_chip === 'ambiguous_investigate' ? 'chip-warning' : 'chip-neutral'}`}>
              {t(STATUS_LABEL_KEY[activeExperiment.status_chip])}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <LanguageToggle />
            <ThemeToggle />
            <button type="button" className="btn btn-small" onClick={logout}>
              {t('common.logOut')}
            </button>
          </div>
        </header>
        <main className="page-outlet" style={{ flex: 1 }}>
          {showNoProjectPrompt ? <NoProjectPrompt /> : showPicker ? <ProjectPickerPrompt /> : <Outlet />}
        </main>
      </div>
    </div>
  )
}
