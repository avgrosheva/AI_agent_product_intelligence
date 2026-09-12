import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, ApiError } from './client'
import type {
  Alert,
  AlertListResponse,
  AlertSeverity,
  AlertStatus,
  ClassifierEvaluationResponse,
  DataQualityReport,
  GenericAIQualitySummaryResponse,
  GenericExperimentListResponse,
  GenericFunnelResponse,
  GenericGuardrailResponse,
  GenericInvestigationResponse,
  GenericMetricTableResponse,
  GenericSessionDetailResponse,
  GenericSessionListResponse,
  MechanismListResponse,
  MeResponse,
  MonitoringConfig,
  MonitoringConfigListResponse,
  NotificationChannel,
  NotificationChannelListResponse,
  OnboardingStatus,
  Organization,
  Project,
  ProjectConfig,
  ProjectConfigPatch,
  ReleaseEvaluation,
  ReleaseEvidenceResponse,
  ReleaseHistoryResponse,
  ReleaseSummaryResponse,
  Review,
  ReviewDecision,
  ReviewQueueResponse,
  SegmentDimensionsResponse,
} from './types'

// Stage 5 established that /metrics and /investigation are cached
// server-side (warm-up + in-process lru_cache); staleTime here just avoids
// re-fetching identical data on every re-render/navigation within one
// browser session, per Stage 6 SS13 ("should not repeatedly trigger
// expensive identical requests"). Not a cache of computed statistics —
// still the exact backend response, only kept around client-side.
const STALE_TIME_MS = 5 * 60 * 1000

export function useClassifierEvaluation() {
  return useQuery({
    queryKey: ['classifier-evaluation'],
    queryFn: () => apiGet<ClassifierEvaluationResponse>('/ai-quality/classifier-evaluation'),
    staleTime: STALE_TIME_MS,
  })
}

// Stage 16: domain/projectId are now explicit params (previously
// hardcoded to "commerce" with an implicit single project) so a support
// project's release decision renders through the same hook.
export function useReleaseSummary(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['release-summary', domain, projectId, experimentId],
    queryFn: () => apiGet<ReleaseSummaryResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/release-summary`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useReleaseHistory(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['release-history', domain, projectId, experimentId],
    queryFn: () => apiGet<ReleaseHistoryResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/release-history`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useReleaseEvidence(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined, evaluationId: string | undefined) {
  return useQuery({
    queryKey: ['release-evidence', domain, projectId, experimentId, evaluationId],
    queryFn: () =>
      apiGet<ReleaseEvidenceResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/release-evaluations/${evaluationId}/evidence`, {
        project_id: projectId,
      }),
    enabled: !!domain && !!projectId && !!experimentId && !!evaluationId,
    staleTime: STALE_TIME_MS,
  })
}

export function useCreateReleaseEvaluation(domain: string | undefined, projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ experimentId, primaryMetric }: { experimentId: string; primaryMetric?: string }) =>
      apiPost<ReleaseEvaluation>(
        `/api/v1/domains/${domain}/experiments/${experimentId}/release-evaluations`,
        undefined,
        { project_id: projectId, ...(primaryMetric ? { primary_metric: primaryMetric } : {}) },
      ),
    onSuccess: (_result, { experimentId }) => {
      queryClient.invalidateQueries({ queryKey: ['release-status', domain, projectId, experimentId] })
      queryClient.invalidateQueries({ queryKey: ['release-summary', domain, projectId, experimentId] })
      queryClient.invalidateQueries({ queryKey: ['release-history', domain, projectId, experimentId] })
    },
  })
}

// -- Stage 16: generic, domain-parametrized equivalents of the legacy
// commerce-only hooks above (useExperiments/useExperimentDetail/
// useExperimentMetrics/useExperimentFunnel/useExperimentGuardrails/
// useInvestigation/useAIQuality/useSessions/useSessionDetail) -- driven
// by (domain, projectId) from ActiveProjectContext instead of an
// implicit single commerce project, so both domains render through the
// same screens. See docs note in ActiveProjectContext.tsx.

export function useDomainMetrics(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['domain-metrics', domain, projectId, experimentId],
    queryFn: () => apiGet<GenericMetricTableResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/metrics`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainGuardrails(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['domain-guardrails', domain, projectId, experimentId],
    queryFn: () => apiGet<GenericGuardrailResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/guardrails`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainFunnel(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['domain-funnel', domain, projectId, experimentId],
    queryFn: () => apiGet<GenericFunnelResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/funnel`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainInvestigation(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined, primaryMetric: string | undefined) {
  return useQuery({
    queryKey: ['domain-investigation', domain, projectId, experimentId, primaryMetric],
    queryFn: () =>
      apiGet<GenericInvestigationResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/investigation`, {
        project_id: projectId,
        primary_metric: primaryMetric,
      }),
    enabled: !!domain && !!projectId && !!experimentId && !!primaryMetric,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainMechanisms(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['domain-mechanisms', domain, projectId],
    queryFn: () => apiGet<MechanismListResponse>(`/api/v1/domains/${domain}/mechanisms`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainAIQuality(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['domain-ai-quality', domain, projectId, experimentId],
    queryFn: () => apiGet<GenericAIQualitySummaryResponse>(`/api/v1/domains/${domain}/experiments/${experimentId}/ai-quality`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: STALE_TIME_MS,
  })
}

export interface DomainSessionFilters {
  experiment_id?: string
  agent_version?: string
  limit?: number
  offset?: number
  // Stage 16: any of this domain's own registered segment dimensions
  // (e.g. platform=android) -- list_domain_sessions applies whichever of
  // these match, ignoring the rest, so callers don't need to know this
  // domain's dimension vocabulary in advance.
  [dimension: string]: string | number | undefined
}

export function useDomainSessions(domain: string | undefined, projectId: string | undefined, filters: DomainSessionFilters) {
  return useQuery({
    queryKey: ['domain-sessions', domain, projectId, filters],
    queryFn: () =>
      apiGet<GenericSessionListResponse>(`/api/v1/domains/${domain}/sessions`, {
        project_id: projectId,
        ...(filters as Record<string, string | number | undefined>),
      }),
    enabled: !!domain && !!projectId,
    staleTime: STALE_TIME_MS,
  })
}

export function useSegmentDimensions(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['segment-dimensions', domain, projectId],
    queryFn: () => apiGet<SegmentDimensionsResponse>(`/api/v1/domains/${domain}/segment-dimensions`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: STALE_TIME_MS,
  })
}

export function useDomainSessionDetail(domain: string | undefined, projectId: string | undefined, sessionId: string | undefined) {
  return useQuery({
    queryKey: ['domain-session', domain, projectId, sessionId],
    queryFn: () => apiGet<GenericSessionDetailResponse>(`/api/v1/domains/${domain}/sessions/${sessionId}`, { project_id: projectId }),
    enabled: !!domain && !!projectId && !!sessionId,
    staleTime: STALE_TIME_MS,
  })
}

// -- Stage 15: onboarding / project-setup ----------------------------
// Short staleTime here (unlike the analytics hooks above) -- onboarding
// state changes as a direct result of the user's own actions in this
// same session (saving config, creating a channel), so the UI must
// reflect that immediately rather than serving a 5-minute-old cache.
const ONBOARDING_STALE_TIME_MS = 0

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => apiGet<MeResponse>('/api/v1/auth/me'),
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useAvailableDomains() {
  return useQuery({
    queryKey: ['domains'],
    queryFn: () => apiGet<string[]>('/api/v1/domains'),
    staleTime: STALE_TIME_MS,
  })
}

export function useCreateOrganization() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => apiPost<Organization>('/api/v1/orgs', { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ orgId, name, domain }: { orgId: string; name: string; domain: string }) =>
      apiPost<Project>(`/api/v1/orgs/${orgId}/projects`, { name, domain }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useProjectConfig(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['project-config', domain, projectId],
    queryFn: () => apiGet<ProjectConfig>(`/api/v1/domains/${domain}/config`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useSaveProjectConfig(domain: string | undefined, projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: ProjectConfigPatch) => apiPut<ProjectConfig>(`/api/v1/domains/${domain}/config`, patch, { project_id: projectId }),
    onSuccess: (result) => {
      queryClient.setQueryData(['project-config', domain, projectId], result)
      queryClient.invalidateQueries({ queryKey: ['onboarding-status', domain, projectId] })
    },
  })
}

export function useOnboardingStatus(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['onboarding-status', domain, projectId],
    queryFn: () => apiGet<OnboardingStatus>(`/api/v1/domains/${domain}/onboarding-status`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useDataQuality(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['data-quality', domain, projectId],
    queryFn: () => apiGet<DataQualityReport>(`/api/v1/domains/${domain}/data-quality`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useGenericExperiments(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['generic-experiments', domain, projectId],
    queryFn: () => apiGet<GenericExperimentListResponse>(`/api/v1/domains/${domain}/experiments`, { project_id: projectId }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useMonitoringConfigs(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['monitoring-configs', domain, projectId],
    queryFn: () => apiGet<MonitoringConfigListResponse>('/api/v1/monitoring/configs', { project_id: projectId, domain }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useCreateMonitoringConfig(domain: string | undefined, projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { experiment_id: string; primary_metric: string; cadence_seconds: number; window_hours: number | null; enabled: boolean }) =>
      apiPost<MonitoringConfig>('/api/v1/monitoring/configs', { domain, ...body }, { project_id: projectId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitoring-configs', domain, projectId] })
      queryClient.invalidateQueries({ queryKey: ['onboarding-status', domain, projectId] })
    },
  })
}

export function useNotificationChannels(domain: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: ['notification-channels', domain, projectId],
    queryFn: () => apiGet<NotificationChannelListResponse>('/api/v1/notifications/channels', { project_id: projectId, domain }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

// Tolerates "no release evaluation has ever run" (404) as a normal,
// expected state -- the overview page shows "not yet evaluated" rather
// than an error for an experiment nobody has shipped yet.
export function useReleaseStatus(domain: string | undefined, projectId: string | undefined, experimentId: string | undefined) {
  return useQuery({
    queryKey: ['release-status', domain, projectId, experimentId],
    queryFn: async () => {
      try {
        return await apiGet<ReleaseEvaluation>(`/api/v1/domains/${domain}/experiments/${experimentId}/release-status`, { project_id: projectId })
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
      }
    },
    enabled: !!domain && !!projectId && !!experimentId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useCreateNotificationChannel(domain: string | undefined, projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { channel_type: 'webhook' | 'slack_webhook'; url: string; enabled: boolean }) =>
      apiPost<NotificationChannel>('/api/v1/notifications/channels', body, { project_id: projectId, domain }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels', domain, projectId] })
      queryClient.invalidateQueries({ queryKey: ['onboarding-status', domain, projectId] })
    },
  })
}

// -- Stage 18 task 1: Alerts ---------------------------------------------

export interface AlertFilters {
  domain?: string
  experiment_id?: string
  status?: AlertStatus
  severity?: AlertSeverity
  limit?: number
  offset?: number
}

export function useAlerts(projectId: string | undefined, filters: AlertFilters) {
  return useQuery({
    queryKey: ['alerts', projectId, filters],
    queryFn: () => apiGet<AlertListResponse>('/api/v1/alerts', { project_id: projectId, ...filters }),
    enabled: !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useAcknowledgeAlert(projectId: string | undefined, filters: AlertFilters) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: string) => apiPost<Alert>(`/api/v1/alerts/${alertId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', projectId, filters] })
    },
  })
}

// -- Stage 18 task 2: Human review queue ----------------------------------

export interface ReviewQueueFilters {
  experiment_id?: string
  mechanism?: string
  unreviewed_only?: boolean
  limit?: number
  offset?: number
}

export function useReviewQueue(domain: string | undefined, projectId: string | undefined, filters: ReviewQueueFilters) {
  return useQuery({
    queryKey: ['review-queue', domain, projectId, filters],
    queryFn: () =>
      apiGet<ReviewQueueResponse>(`/api/v1/domains/${domain}/review-queue`, {
        project_id: projectId,
        ...(filters as Record<string, string | number | boolean | undefined>),
      }),
    enabled: !!domain && !!projectId,
    staleTime: ONBOARDING_STALE_TIME_MS,
  })
}

export function useSubmitReview(domain: string | undefined, projectId: string | undefined, filters: ReviewQueueFilters) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, failureMode, decision, correctedMechanism, note }: {
      sessionId: string
      failureMode: string
      decision: ReviewDecision
      correctedMechanism?: string
      note?: string
    }) =>
      apiPost<Review>(`/api/v1/domains/${domain}/sessions/${sessionId}/attributions/${failureMode}/review`, {
        decision, corrected_mechanism: correctedMechanism, note,
      }, { project_id: projectId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-queue', domain, projectId, filters] })
    },
  })
}

/** Stage 21: lets SessionDetail submit a review decision in place --
 * previously the only way to confirm/reject/correct an attribution was
 * the Review Queue table, so opening a session from the queue to read
 * its full evidence (transcript, tool calls) lost the review controls
 * entirely and forced a trip back. Invalidates this session's own
 * query (so its status updates immediately) and every review-queue
 * view regardless of filters (a prefix match, not the exact-filters
 * key useSubmitReview uses), since which queue view the user came from
 * isn't known here. */
export function useSubmitSessionReview(domain: string | undefined, projectId: string | undefined, sessionId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ failureMode, decision, correctedMechanism, note }: {
      failureMode: string
      decision: ReviewDecision
      correctedMechanism?: string
      note?: string
    }) =>
      apiPost<Review>(`/api/v1/domains/${domain}/sessions/${sessionId}/attributions/${failureMode}/review`, {
        decision, corrected_mechanism: correctedMechanism, note,
      }, { project_id: projectId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domain-session', domain, projectId, sessionId] })
      queryClient.invalidateQueries({ queryKey: ['review-queue'] })
    },
  })
}
