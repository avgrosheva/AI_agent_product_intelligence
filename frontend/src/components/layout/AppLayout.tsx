import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useActiveExperiment } from '../../state/ActiveExperimentContext'
import { useActiveProject } from '../../state/ActiveProjectContext'
import { useAuth } from '../../state/AuthContext'

const STATUS_LABEL: Record<string, string> = {
  ambiguous_investigate: 'Needs investigation',
  no_regression_detected: 'No regression detected',
  not_yet_investigated: 'Not yet investigated',
}

// Routes that manage project selection themselves (ProjectOverview already
// has its own "no project selected" state with a link to /setup; the
// onboarding wizard's first step IS the project picker/creator) -- these
// must stay reachable no matter which project-selection state the rest of
// the shell is in, otherwise a brand-new user with zero projects, or one
// who needs to pick among several, would have no way to get there.
const PROJECT_MANAGEMENT_PATHS = ['/setup', '/project']

function ProjectSwitcher() {
  const { projects, activeProjectId, setActiveProjectId } = useActiveProject()
  if (projects.length < 2) return null
  return (
    <label className="project-switcher">
      <span className="text-muted">Project</span>
      <select
        value={activeProjectId ?? ''}
        onChange={(e) => setActiveProjectId(e.target.value)}
        aria-label="Switch active project"
      >
        {!activeProjectId && (
          <option value="" disabled>
            Select a project…
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
  const { projects, setActiveProjectId } = useActiveProject()
  return (
    <div className="page">
      <div className="card" style={{ maxWidth: 480, margin: '48px auto' }}>
        <div className="card-header">
          <h2>Select a project</h2>
          <p>You belong to more than one project. Pick which one to work in -- this app never guesses for you.</p>
        </div>
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
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function NoProjectPrompt() {
  return (
    <div className="page">
      <div className="state-box" style={{ maxWidth: 480, margin: '48px auto', textAlign: 'center' }}>
        <p>You don't have a project yet.</p>
        <Link to="/setup" className="btn btn-primary">
          Set up your first project
        </Link>
      </div>
    </div>
  )
}

export function AppLayout() {
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
          <div className="sidebar-brand">AI Agent Product Intelligence</div>
          <div className="sidebar-brand-sub">
            {activeProject ? `${activeProject.name} · ${activeProject.domain}` : projectsLoading ? 'Loading…' : 'No project selected'}
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Overview
          </NavLink>
          {expPath ? (
            <>
              <NavLink to={expPath} end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Experiment
              </NavLink>
              <NavLink to={`${expPath}/release`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Release Decision
              </NavLink>
              <NavLink to={`${expPath}/investigation`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Investigation
              </NavLink>
            </>
          ) : (
            <>
              <span className="sidebar-link sidebar-link-disabled" title="Select a project with at least one experiment first" aria-disabled="true">Experiment</span>
              <span className="sidebar-link sidebar-link-disabled" title="Select a project with at least one experiment first" aria-disabled="true">Release Decision</span>
              <span className="sidebar-link sidebar-link-disabled" title="Select a project with at least one experiment first" aria-disabled="true">Investigation</span>
            </>
          )}
          <NavLink to="/sessions" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Sessions
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Alerts
          </NavLink>
          <NavLink to="/review-queue" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Review Queue
          </NavLink>
          {expPath ? (
            <NavLink to={`${expPath}/ai-quality`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
              AI Quality
            </NavLink>
          ) : (
            <span className="sidebar-link sidebar-link-disabled" title="Select a project with at least one experiment first" aria-disabled="true">AI Quality</span>
          )}
          <NavLink to="/project" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Project Overview
          </NavLink>
          <NavLink to="/setup" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Project Setup
          </NavLink>
        </nav>
        <ProjectSwitcher />
      </aside>
      <div className="main-area">
        <header className="top-bar">
          <div className="active-experiment">
            <span className="text-muted">Active experiment:</span>
            {activeExperiment ? (
              <>
                <strong>{activeExperiment.name}</strong>
                <span className="text-muted">({activeExperiment.control_version} vs {activeExperiment.treatment_version})</span>
              </>
            ) : (
              <span className="text-muted">none selected</span>
            )}
          </div>
          {activeExperiment && (
            <span className={`chip ${activeExperiment.status_chip === 'ambiguous_investigate' ? 'chip-warning' : 'chip-neutral'}`}>
              {STATUS_LABEL[activeExperiment.status_chip]}
            </span>
          )}
          <button type="button" className="btn btn-small" onClick={logout}>
            Log out
          </button>
        </header>
        <main className="page-outlet" style={{ flex: 1 }}>
          {showNoProjectPrompt ? <NoProjectPrompt /> : showPicker ? <ProjectPickerPrompt /> : <Outlet />}
        </main>
      </div>
    </div>
  )
}
