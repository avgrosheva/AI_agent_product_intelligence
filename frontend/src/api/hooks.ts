import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'
import type {
  AIQualitySummaryResponse,
  ClassifierEvaluationResponse,
  ExperimentDetail,
  ExperimentListResponse,
  FunnelResponse,
  GuardrailResponse,
  InvestigationLens,
  InvestigationResponse,
  MetricTableResponse,
  ReleaseSummaryResponse,
  SessionDetail,
  SessionListResponse,
} from './types'

// Stage 5 established that /metrics and /investigation are cached
// server-side (warm-up + in-process lru_cache); staleTime here just avoids
// re-fetching identical data on every re-render/navigation within one
// browser session, per Stage 6 SS13 ("should not repeatedly trigger
// expensive identical requests"). Not a cache of computed statistics —
// still the exact backend response, only kept around client-side.
const STALE_TIME_MS = 5 * 60 * 1000

export function useExperiments() {
  return useQuery({
    queryKey: ['experiments'],
    queryFn: () => apiGet<ExperimentListResponse>('/experiments'),
    staleTime: STALE_TIME_MS,
  })
}

export function useExperimentDetail(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['experiment', experimentId],
    queryFn: () => apiGet<ExperimentDetail>(`/experiments/${experimentId}`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useExperimentMetrics(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['experiment', experimentId, 'metrics'],
    queryFn: () => apiGet<MetricTableResponse>(`/experiments/${experimentId}/metrics`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useExperimentFunnel(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['experiment', experimentId, 'funnel'],
    queryFn: () => apiGet<FunnelResponse>(`/experiments/${experimentId}/funnel`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useExperimentGuardrails(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['experiment', experimentId, 'guardrails'],
    queryFn: () => apiGet<GuardrailResponse>(`/experiments/${experimentId}/guardrails`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useInvestigation(experimentId: string | undefined, lens: InvestigationLens) {
  return useQuery({
    queryKey: ['experiment', experimentId, 'investigation', lens],
    queryFn: () => apiGet<InvestigationResponse>(`/experiments/${experimentId}/investigation`, { lens }),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useAIQuality(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['experiment', experimentId, 'ai-quality'],
    queryFn: () => apiGet<AIQualitySummaryResponse>(`/experiments/${experimentId}/ai-quality`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useClassifierEvaluation() {
  return useQuery({
    queryKey: ['classifier-evaluation'],
    queryFn: () => apiGet<ClassifierEvaluationResponse>('/ai-quality/classifier-evaluation'),
    staleTime: STALE_TIME_MS,
  })
}

export interface SessionFilters {
  experiment_id?: string
  agent_version?: string
  requested_category?: string
  constraint_count_bucket?: string
  platform?: string
  device_tier?: string
  locale?: string
  persona?: string
  outcome?: string
  failure_mode?: string
  limit?: number
  offset?: number
}

export function useSessions(filters: SessionFilters) {
  return useQuery({
    queryKey: ['sessions', filters],
    queryFn: () => apiGet<SessionListResponse>('/sessions', filters as Record<string, string | number | undefined>),
    staleTime: STALE_TIME_MS,
  })
}

export function useSessionDetail(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => apiGet<SessionDetail>(`/sessions/${sessionId}`),
    enabled: !!sessionId,
    staleTime: STALE_TIME_MS,
  })
}

// Stage 14: the release-summary endpoint lives under the generic,
// project-scoped domain API (unlike the commerce-only routes above) —
// this app has exactly one commerce project per logged-in user, so the
// backend resolves it implicitly with no project_id needed.
export function useReleaseSummary(experimentId: string | undefined) {
  return useQuery({
    queryKey: ['release-summary', experimentId],
    queryFn: () => apiGet<ReleaseSummaryResponse>(`/api/v1/domains/commerce/experiments/${experimentId}/release-summary`),
    enabled: !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}
