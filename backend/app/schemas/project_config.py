"""Stage 12 tasks 4-6: request/response contracts for persisted
per-project configuration and the onboarding-readiness status
(backend.app.routers.domains's config/onboarding-status endpoints)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProjectConfigRequest(BaseModel):
    """A full-replace PUT body — any field omitted (left None) means "no
    override for this," falling back to the domain's static default
    (Stage 12 task 7)."""

    primary_metric: str | None = None
    metrics: dict | None = None
    guardrails: dict | None = None
    segment_dimensions: dict | None = None
    economics: dict | None = None
    monitoring_cadence_seconds: int | None = None
    enabled_notification_rules: list[str] | None = None


class AvailableMetricSchema(BaseModel):
    name: str
    label: str
    metric_type: str
    direction: str
    semantic_class: str
    is_inferential: bool
    is_descriptive: bool
    # The analytics_base_df column this metric actually reads, when known
    # (None for a metric with no simple 1-column binding). Round-tripped
    # back into a metrics-JSON entry's "value_column" by the onboarding
    # UI when a project customizes its metric list, so adding one new
    # metric never silently drops how the existing ones are computed.
    value_column: str | None


class AvailableGuardrailSchema(BaseModel):
    name: str
    metric: str
    column: str
    aggregation: str
    kind: str
    direction: str
    threshold: float
    severity: str
    enabled: bool


class ProjectConfigSchema(BaseModel):
    project_id: str
    primary_metric: str | None
    metrics: dict | None
    guardrails: dict | None
    segment_dimensions: dict | None
    economics: dict | None
    monitoring_cadence_seconds: int | None
    enabled_notification_rules: list[str]
    created_at: datetime | None
    updated_at: datetime | None
    # Stage 15 tasks 3-5: read-only projections of the domain's CURRENT
    # effective state (persisted override if set, else the static
    # default) — exactly what backend.project_config.overrides already
    # computes for the adapter itself, exposed here so a UI can offer
    # dropdowns/checklists instead of asking a PM to write JSON.
    available_metrics: list[AvailableMetricSchema]
    available_guardrails: list[AvailableGuardrailSchema]
    available_context_fields: list[str]


class OnboardingStatusResponse(BaseModel):
    project_id: str
    domain: str
    ingestion_connected: bool
    data_received: bool
    primary_metric_configured: bool
    guardrails_configured: bool
    data_quality_status: str
    monitoring_enabled: bool
    notifications_configured: bool
