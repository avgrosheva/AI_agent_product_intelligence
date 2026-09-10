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
