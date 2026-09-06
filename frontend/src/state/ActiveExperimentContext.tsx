import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useExperiments } from '../api/hooks'
import type { ExperimentSummary } from '../api/types'

const STORAGE_KEY = 'aipi.activeExperimentId'

interface ActiveExperimentContextValue {
  activeExperimentId: string | null
  setActiveExperimentId: (id: string) => void
  activeExperiment: ExperimentSummary | null
  experiments: ExperimentSummary[]
  isLoading: boolean
  error: string | null
}

const ActiveExperimentContext = createContext<ActiveExperimentContextValue | null>(null)

/** Keeps "the active experiment" visible and consistent across all
 * screens (Stage 6 SS2: "The active experiment should remain visible in
 * the interface"). Defaults to the first experiment returned by the API
 * once loaded — with a single demo experiment this is invisible to the
 * user, but the mechanism generalizes if a second experiment is added. */
export function ActiveExperimentProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, error } = useExperiments()
  const [activeExperimentId, setActiveExperimentIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY)
    } catch {
      return null
    }
  })

  const experiments = useMemo(() => data?.experiments ?? [], [data])

  useEffect(() => {
    if (!activeExperimentId && experiments.length > 0) {
      setActiveExperimentIdState(experiments[0].experiment_id)
    }
  }, [activeExperimentId, experiments])

  function setActiveExperimentId(id: string) {
    setActiveExperimentIdState(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
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
