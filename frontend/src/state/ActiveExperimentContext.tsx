import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { useGenericExperiments } from '../api/hooks'
import type { GenericExperimentSummary } from '../api/types'
import { useActiveProject } from './ActiveProjectContext'

function storageKeyFor(projectId: string | null): string | null {
  return projectId ? `aipi.activeExperimentId.${projectId}` : null
}

interface ActiveExperimentContextValue {
  activeExperimentId: string | null
  setActiveExperimentId: (id: string) => void
  activeExperiment: GenericExperimentSummary | null
  experiments: GenericExperimentSummary[]
  isLoading: boolean
  error: string | null
}

const ActiveExperimentContext = createContext<ActiveExperimentContextValue | null>(null)

/** Stage 16: which experiment is active WITHIN the active project
 * (ActiveProjectContext) -- domain-agnostic, driven by the generic
 * experiments list for that project's own domain (useGenericExperiments).
 *
 * Stage 17 fix: `activeExperimentId` is now derived synchronously on every
 * render from (storageKey, overrides, experiments, query state) via
 * useMemo -- there is no state that "used to belong" to a previous
 * project for a stale render to expose. The earlier version kept
 * activeExperimentId in its own useState and reset it in a useEffect keyed
 * on storageKey; effects run AFTER the render that already switched
 * domain/projectId commits, so for exactly one render, every consumer
 * calling useDomainX(domain, projectId, activeExperimentId) saw the NEW
 * project paired with the OLD project's experiment id -- the source of
 * the transient 404s during project switching (Stage 16 audit). Now:
 * while the new project's experiment list hasn't loaded yet (`data` is
 * still undefined for the new query key), activeExperimentId is `null`,
 * full stop -- every useDomainX hook's `enabled: !!experimentId` guard
 * then correctly sends no request at all until real data exists for the
 * NEW project, never a request scoped to the old one. */
export function ActiveExperimentProvider({ children }: { children: ReactNode }) {
  const { activeProjectId, activeProject } = useActiveProject()
  const domain = activeProject?.domain
  const { data, isLoading, error } = useGenericExperiments(domain, activeProjectId ?? undefined)
  const storageKey = storageKeyFor(activeProjectId)
  const experiments = useMemo(() => data?.experiments ?? [], [data])

  // In-memory overrides from an explicit setActiveExperimentId call,
  // keyed by storageKey. Looked up by the CURRENT storageKey every
  // render (never carried over from a different project's key) --
  // localStorage remains the source for a value persisted in an earlier
  // session, but a live override always wins within this session so a
  // click takes effect on the same render, not after a localStorage
  // round-trip.
  const [overrides, setOverrides] = useState<Record<string, string>>({})

  const persistedExperimentId = useMemo(() => {
    if (!storageKey) return null
    if (overrides[storageKey]) return overrides[storageKey]
    try {
      return localStorage.getItem(storageKey)
    } catch {
      return null
    }
  }, [storageKey, overrides])

  const activeExperimentId = useMemo(() => {
    // Still fetching (or no project selected at all) -- never fall back
    // to a previous project's id or a guess; a consumer sees "no active
    // experiment yet" and sends no request, rather than one scoped to
    // whatever used to be active.
    if (data === undefined) return null
    if (persistedExperimentId && experiments.some((e) => e.experiment_id === persistedExperimentId)) {
      return persistedExperimentId
    }
    return experiments[0]?.experiment_id ?? null
  }, [data, persistedExperimentId, experiments])

  function setActiveExperimentId(id: string) {
    if (!storageKey) return
    setOverrides((prev) => ({ ...prev, [storageKey]: id }))
    try {
      localStorage.setItem(storageKey, id)
    } catch {
      // best-effort only; navigation still works without persistence
    }
  }

  const activeExperiment = experiments.find((e) => e.experiment_id === activeExperimentId) ?? null

  return (
    <ActiveExperimentContext.Provider
      value={{
        activeExperimentId,
        setActiveExperimentId,
        activeExperiment,
        experiments,
        isLoading,
        error: error ? (error as Error).message : null,
      }}
    >
      {children}
    </ActiveExperimentContext.Provider>
  )
}

export function useActiveExperiment() {
  const ctx = useContext(ActiveExperimentContext)
  if (!ctx) throw new Error('useActiveExperiment must be used within ActiveExperimentProvider')
  return ctx
}
