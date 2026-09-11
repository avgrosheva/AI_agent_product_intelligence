import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMe } from '../api/hooks'
import type { Project } from '../api/types'

const STORAGE_KEY = 'aipi.activeProjectId'

interface ActiveProjectContextValue {
  activeProjectId: string | null
  activeProject: Project | null
  setActiveProjectId: (id: string) => void
  projects: Project[]
  isLoading: boolean
  error: string | null
  /** True once projects have loaded and there is more than one, with no
   * still-valid explicit choice on record -- the app shell must render a
   * picker rather than act on any one of them. */
  needsExplicitSelection: boolean
}

const ActiveProjectContext = createContext<ActiveProjectContextValue | null>(null)

/** Stage 15/16: which project (and therefore which domain) the WHOLE
 * authenticated app operates on -- every screen reads this (Overview,
 * Experiment, Investigation, Release Decision, Sessions, AI Quality,
 * Project Overview, Setup), not just the onboarding screens Stage 15
 * originally built it for.
 *
 * Selection is never silent. With exactly one project there is no real
 * choice to make, so it's applied automatically. With more than one, the
 * user must explicitly pick -- AppLayout renders a picker whenever
 * `needsExplicitSelection` is true -- and only that explicit choice, never
 * `projects[0]`, is applied and persisted. A previously-persisted choice
 * that no longer belongs to this account (a different login, a removed
 * project) is discarded outright, never silently swapped for a different
 * project the user didn't pick. */
export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, error } = useMe()
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY)
    } catch {
      return null
    }
  })

  const projects = useMemo(() => data?.projects ?? [], [data])

  useEffect(() => {
    if (isLoading) return
    if (activeProjectId && !projects.some((p) => p.project_id === activeProjectId)) {
      setActiveProjectIdState(null)
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        // best-effort only
      }
      return
    }
    if (!activeProjectId && projects.length === 1) {
      // Not a "default among choices" -- there is only one project, so
      // applying it is the only thing selection could ever mean.
      setActiveProjectId(projects[0].project_id)
    }
  }, [activeProjectId, projects, isLoading])

  function setActiveProjectId(id: string) {
    setActiveProjectIdState(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      // best-effort only; navigation still works without persistence
    }
  }

  const activeProject = projects.find((p) => p.project_id === activeProjectId) ?? null
  const needsExplicitSelection = !isLoading && !activeProjectId && projects.length > 1

  return (
    <ActiveProjectContext.Provider
      value={{
        activeProjectId,
        activeProject,
        setActiveProjectId,
        projects,
        isLoading,
        error: error ? (error as Error).message : null,
        needsExplicitSelection,
      }}
    >
      {children}
    </ActiveProjectContext.Provider>
  )
}

export function useActiveProject() {
  const ctx = useContext(ActiveProjectContext)
  if (!ctx) throw new Error('useActiveProject must be used within ActiveProjectProvider')
  return ctx
}
