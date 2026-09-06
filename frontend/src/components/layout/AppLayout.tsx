import { NavLink, Outlet } from 'react-router-dom'
import { useActiveExperiment } from '../../state/ActiveExperimentContext'

const STATUS_LABEL: Record<string, string> = {
  ambiguous_investigate: 'Needs investigation',
  no_regression_detected: 'No regression detected',
  not_yet_investigated: 'Not yet investigated',
}

export function AppLayout() {
  const { activeExperimentId, activeExperiment } = useActiveExperiment()
  const expPath = activeExperimentId ? `/experiments/${activeExperimentId}` : '/'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="sidebar-brand">AI Agent Product Intelligence</div>
          <div className="sidebar-brand-sub">Conversational commerce experiments</div>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Overview
          </NavLink>
          <NavLink to={expPath} end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Experiment
          </NavLink>
          <NavLink to={`${expPath}/investigation`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Investigation
          </NavLink>
          <NavLink to="/sessions" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            Sessions
          </NavLink>
          <NavLink to={`${expPath}/ai-quality`} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            AI Quality
          </NavLink>
        </nav>
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
        </header>
        <main className="page-outlet" style={{ flex: 1 }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
