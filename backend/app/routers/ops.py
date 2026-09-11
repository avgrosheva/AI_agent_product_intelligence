"""Stage 18 task 7: read-only operational health, safe to expose to any
authenticated user (it is a deployment-health signal, not tenant data —
see backend.app.schemas.ops's field-level comments for exactly what's
deliberately left out to keep it that way). Not project-scoped: this
reports on the deployment as a whole, the same shape a Kubernetes
liveness/readiness probe or an uptime-monitoring dashboard would read.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import text

from backend.analytics.cache_utils import investigation_cache, metrics_table_cache
from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import get_engine
from backend.app.schemas.ops import (
    CacheStatsSchema,
    ConnectorAvailabilitySchema,
    DatabaseHealthSchema,
    HealthResponse,
    LatestMonitoringRunSchema,
    SchedulerHealthSchema,
)
from backend.monitoring.lease import get_lease_state
from backend.monitoring.scheduler import SCHEDULER_LEASE_KEY, scheduler_enabled_via_env
from backend.monitoring.service import get_latest_monitoring_run_overall

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


def _database_health() -> DatabaseHealthSchema:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return DatabaseHealthSchema(connected=True)
    except Exception as exc:
        # The exception's own message can legitimately contain a
        # connection string fragment (host/port/dbname) in some drivers —
        # never the password (psycopg does not include it), but truncate
        # defensively anyway so this never becomes a place a stack trace
        # accidentally leaks more than "the database is unreachable."
        return DatabaseHealthSchema(connected=False, error=str(exc)[:200])


def _scheduler_health() -> SchedulerHealthSchema:
    lease = get_lease_state(get_engine(), SCHEDULER_LEASE_KEY)
    return SchedulerHealthSchema(
        enabled_via_env=scheduler_enabled_via_env(),
        lease_held=lease is not None and lease.is_active,
        holder_id=lease.holder_id if lease else None,
        lease_acquired_at=lease.acquired_at if lease else None,
        lease_expires_at=lease.expires_at if lease else None,
    )


def _connector_availability() -> ConnectorAvailabilitySchema:
    return ConnectorAvailabilitySchema(
        langfuse_configured=bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(os.environ.get("LANGFUSE_SECRET_KEY")),
        postgres_business_configured=bool(os.environ.get("BUSINESS_DB_HOST")) and bool(os.environ.get("BUSINESS_DB_NAME")),
    )


def _cache_stats() -> CacheStatsSchema:
    return CacheStatsSchema(
        metrics_table_cache_size=metrics_table_cache.size, metrics_table_cache_maxsize=metrics_table_cache.maxsize,
        investigation_cache_size=investigation_cache.size, investigation_cache_maxsize=investigation_cache.maxsize,
    )


@router.get("/health", response_model=HealthResponse)
def get_health(user: CurrentUser = Depends(get_current_user)) -> HealthResponse:
    latest_run = get_latest_monitoring_run_overall(get_engine())
    return HealthResponse(
        database=_database_health(),
        scheduler=_scheduler_health(),
        connectors=_connector_availability(),
        cache=_cache_stats(),
        latest_monitoring_run=(
            LatestMonitoringRunSchema(status=latest_run.status, started_at=latest_run.started_at, completed_at=latest_run.completed_at)
            if latest_run is not None
            else None
        ),
    )
