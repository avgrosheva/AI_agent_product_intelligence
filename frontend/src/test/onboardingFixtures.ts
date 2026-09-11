import { vi } from 'vitest'
import type {
  AvailableGuardrail,
  AvailableMetric,
  DataQualityReport,
  GenericExperimentListResponse,
  GuardrailConfigEntry,
  MeResponse,
  MonitoringConfigListResponse,
  NotificationChannelListResponse,
  OnboardingStatus,
  Organization,
  Project,
  ProjectConfig,
} from '../api/types'

// Deliberately NOT importing ApiError from '../api/client' here: this
// module is dynamically imported from inside that module's own
// vi.mock() factory (see any *.test.tsx using it), and a top-level
// import of the mocked module from within its own mock factory's
// dependency graph deadlocks vitest (the factory never resolves). A
// duck-typed lookalike (same shape formatValidationErrors checks via
// `instanceof`) would break that check, so callers pass the real
// ApiError class in via createOnboardingApiMocks(ApiError) instead.
type ApiErrorLike = new (status: number, detail: string) => Error

export const PROJECT_ID = 'proj-0001'
export const ORG_ID = 'org-0001'
export const DOMAIN = 'support'

const BASE_METRIC: AvailableMetric = {
  name: 'resolution_rate', label: 'Resolution rate', metric_type: 'rate', direction: 'higher_is_better',
  semantic_class: 'outcome', is_inferential: true, is_descriptive: true, value_column: 'resolved',
}

const BASE_GUARDRAIL: AvailableGuardrail = {
  name: 'escalation_rate_guardrail', metric: 'escalation_rate', column: 'escalated', aggregation: 'cluster_mean',
  kind: 'absolute', direction: 'increase_is_bad', threshold: 0.05, severity: 'blocking', enabled: true,
}

/** Mutable in-memory stand-in for the backend, shared across a single
 * test file's mocked apiGet/apiPost/apiPut. Mutate its fields in
 * beforeEach via resetOnboardingServer() rather than reassigning the
 * export -- the vi.mock closures below capture this exact object. */
export const server: {
  config: ProjectConfig
  status: OnboardingStatus
  me: MeResponse
  domains: string[]
  quality: DataQualityReport
  experiments: GenericExperimentListResponse
  monitoring: MonitoringConfigListResponse
  channels: NotificationChannelListResponse
} = {} as never

export function resetOnboardingServer() {
  server.config = {
    project_id: PROJECT_ID, primary_metric: null, metrics: null, guardrails: null, segment_dimensions: null,
    economics: null, monitoring_cadence_seconds: null, enabled_notification_rules: [],
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
    available_metrics: [BASE_METRIC],
    available_guardrails: [BASE_GUARDRAIL],
    available_context_fields: ['ticket_category'],
  }
  server.status = {
    project_id: PROJECT_ID, domain: DOMAIN, ingestion_connected: true, data_received: false,
    primary_metric_configured: false, guardrails_configured: true, data_quality_status: 'healthy',
    monitoring_enabled: false, notifications_configured: false,
  }
  server.me = {
    user: { user_id: 'user-1', email: 'demo@example.com', created_at: '2026-01-01T00:00:00Z' },
    memberships: [{ membership_id: 'mem-1', org_id: ORG_ID, user_id: 'user-1', email: 'demo@example.com', role: 'admin', created_at: '2026-01-01T00:00:00Z' }],
    projects: [{ project_id: PROJECT_ID, org_id: ORG_ID, name: 'Test Support Project', domain: DOMAIN, created_at: '2026-01-01T00:00:00Z' }],
  }
  server.domains = ['support', 'commerce']
  server.quality = { project_id: PROJECT_ID, domain: DOMAIN, status: 'healthy', generated_at: '2026-09-01T00:00:00Z', checks: [] }
  server.experiments = {
    domain: DOMAIN,
    experiments: [{
      experiment_id: 'exp-1', name: 'Support Bot Rollout', control_version: 'v1', treatment_version: 'v2',
      start_date: null, end_date: null, n_sessions: null, n_users: null, north_star_metric: null, status_chip: 'not_yet_investigated',
    }],
  }
  server.monitoring = { configs: [] }
  server.channels = { channels: [] }
}
resetOnboardingServer()

/** How many times config PUT should fail before succeeding -- lets a
 * test exercise real error-surfacing without needing a UI path that
 * can construct an actually-invalid request (most forms here are
 * dropdown-constrained precisely so they can't). */
export let failNextConfigSaves = 0
export function setFailNextConfigSaves(n: number) {
  failNextConfigSaves = n
}

function recomputeAvailableGuardrails(entries: GuardrailConfigEntry[]): AvailableGuardrail[] {
  return entries.map((g) => ({
    name: g.name, metric: g.metric ?? '', column: g.column, aggregation: g.aggregation,
    kind: g.kind ?? 'ratio', direction: g.direction ?? 'increase_is_bad', threshold: g.threshold,
    severity: g.severity ?? 'blocking', enabled: g.enabled ?? true,
  }))
}

let mocks: { apiGet: ReturnType<typeof vi.fn>; apiPut: ReturnType<typeof vi.fn>; apiPost: ReturnType<typeof vi.fn> } | null = null

/** Builds (once per test file -- memoized) the apiGet/apiPut/apiPost
 * mocks against `server` above. Takes the real ApiError class as a
 * parameter -- pass `actual.ApiError` from inside the test's own
 * vi.mock('../../api/client', ...) factory, where `actual` came from
 * vi.importActual. */
export function createOnboardingApiMocks(ApiErrorClass: ApiErrorLike) {
  if (mocks) return mocks

  const apiGet = vi.fn((path: string) => {
    if (path === '/api/v1/auth/me') return Promise.resolve(server.me)
    if (path === '/api/v1/domains') return Promise.resolve(server.domains)
    if (path === `/api/v1/domains/${DOMAIN}/config`) return Promise.resolve(server.config)
    if (path === `/api/v1/domains/${DOMAIN}/onboarding-status`) return Promise.resolve(server.status)
    if (path === `/api/v1/domains/${DOMAIN}/data-quality`) return Promise.resolve(server.quality)
    if (path === `/api/v1/domains/${DOMAIN}/experiments`) return Promise.resolve(server.experiments)
    if (path === '/api/v1/monitoring/configs') return Promise.resolve(server.monitoring)
    if (path === '/api/v1/notifications/channels') return Promise.resolve(server.channels)
    if (path.startsWith(`/api/v1/domains/${DOMAIN}/experiments/`) && path.endsWith('/release-status')) {
      return Promise.reject(new ApiErrorClass(404, 'No release evaluation has been run yet'))
    }
    return Promise.reject(new Error(`Unmocked GET in onboarding test: ${path}`))
  })

  const apiPut = vi.fn((path: string, body: Record<string, unknown>) => {
    if (path === `/api/v1/domains/${DOMAIN}/config`) {
      if (failNextConfigSaves > 0) {
        failNextConfigSaves -= 1
        return Promise.reject(new ApiErrorClass(422, JSON.stringify([{ field: 'guardrails', message: "guardrail 'g1' references unknown metric 'totally_unknown'" }])))
      }
      server.config = {
        ...server.config,
        ...body,
        available_metrics: server.config.available_metrics,
        available_guardrails: body.guardrails ? recomputeAvailableGuardrails((body.guardrails as { guardrails: GuardrailConfigEntry[] }).guardrails) : server.config.available_guardrails,
        available_context_fields: server.config.available_context_fields,
      } as ProjectConfig
      return Promise.resolve(server.config)
    }
    return Promise.reject(new Error(`Unmocked PUT in onboarding test: ${path}`))
  })

  const apiPost = vi.fn((path: string, body: Record<string, unknown>) => {
    if (path === '/api/v1/orgs') {
      const org: Organization = { org_id: 'org-new', name: String(body.name), created_at: '2026-09-01T00:00:00Z' }
      server.me = { ...server.me, memberships: [...server.me.memberships, { membership_id: 'mem-new', org_id: org.org_id, user_id: server.me.user.user_id, email: server.me.user.email, role: 'admin', created_at: org.created_at }] }
      return Promise.resolve(org)
    }
    if (path.startsWith('/api/v1/orgs/') && path.endsWith('/projects')) {
      const orgId = path.split('/')[4]
      const project: Project = { project_id: 'proj-new', org_id: orgId, name: String(body.name), domain: String(body.domain), created_at: '2026-09-01T00:00:00Z' }
      server.me = { ...server.me, projects: [...server.me.projects, project] }
      return Promise.resolve(project)
    }
    if (path === '/api/v1/monitoring/configs') {
      server.monitoring = { configs: [...server.monitoring.configs, { config_id: 'mon-new', project_id: PROJECT_ID, domain: DOMAIN, experiment_id: String(body.experiment_id), primary_metric: String(body.primary_metric), cadence_seconds: Number(body.cadence_seconds), window_hours: body.window_hours as number | null, enabled: Boolean(body.enabled), created_at: '2026-09-01T00:00:00Z' }] }
      server.status = { ...server.status, monitoring_enabled: Boolean(body.enabled) }
      return Promise.resolve(server.monitoring.configs[server.monitoring.configs.length - 1])
    }
    if (path === '/api/v1/notifications/channels') {
      const url = String(body.url)
      server.channels = { channels: [...server.channels.channels, { channel_id: 'chan-new', project_id: PROJECT_ID, channel_type: body.channel_type as 'webhook' | 'slack_webhook', url_preview: `…${url.slice(-6)}`, enabled: Boolean(body.enabled), created_at: '2026-09-01T00:00:00Z' }] }
      return Promise.resolve(server.channels.channels[server.channels.channels.length - 1])
    }
    return Promise.reject(new Error(`Unmocked POST in onboarding test: ${path}`))
  })

  mocks = { apiGet, apiPut, apiPost }
  return mocks
}

export function resetOnboardingMocks() {
  resetOnboardingServer()
  failNextConfigSaves = 0
  mocks?.apiGet.mockClear()
  mocks?.apiPut.mockClear()
  mocks?.apiPost.mockClear()
}
