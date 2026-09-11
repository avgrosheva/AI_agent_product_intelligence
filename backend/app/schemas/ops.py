from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DatabaseHealthSchema(BaseModel):
    connected: bool
    error: str | None = None


class SchedulerHealthSchema(BaseModel):
    enabled_via_env: bool
    lease_held: bool
    holder_id: str | None = None
    lease_acquired_at: datetime | None = None
    lease_expires_at: datetime | None = None


class ConnectorAvailabilitySchema(BaseModel):
    # Booleans only -- whether the required environment variables are
    # SET, never their values (backend.app.routers.ops never reads the
    # actual credentials to answer this).
    langfuse_configured: bool
    postgres_business_configured: bool


class CacheStatsSchema(BaseModel):
    metrics_table_cache_size: int
    metrics_table_cache_maxsize: int
    investigation_cache_size: int
    investigation_cache_maxsize: int


class LatestMonitoringRunSchema(BaseModel):
    # Deliberately just status + timing -- no project_id, experiment_id,
    # config_id, or failure_reason. Those identify WHOSE data a run
    # touched, or may echo exception text; this endpoint is an aggregate
    # deployment-health signal any authenticated user can read; it must
    # never let one tenant learn what another tenant's experiment is
    # named, still less any detail from its failure_reason.
    status: str
    started_at: datetime
    completed_at: datetime | None


class HealthResponse(BaseModel):
    database: DatabaseHealthSchema
    scheduler: SchedulerHealthSchema
    connectors: ConnectorAvailabilitySchema
    cache: CacheStatsSchema
    latest_monitoring_run: LatestMonitoringRunSchema | None
