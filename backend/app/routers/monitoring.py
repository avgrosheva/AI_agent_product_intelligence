"""Monitoring configuration and run-history API (Stage 11 tasks 1-2/7).
Same auth pattern as ingestion/the connectors: explicit `project_id`
query param (there is no single `domain` path segment here, since a
project could in principle watch experiments across domains — though in
practice one project has exactly one domain), "analyst" role or higher
to create a config or trigger an on-demand run, any member to read.

On-demand runs are dispatched via FastAPI's BackgroundTasks (Stage 11
task 1: "background jobs, not request-blocking loops") — the endpoint
creates the "running" MonitoringRun row and returns its id immediately;
the actual Investigation-engine computation happens after the response
is sent, and the caller polls run-history/latest-status to see it finish.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_adapter, get_engine
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project
from backend.app.schemas.monitoring import (
    MonitoringConfigCreateRequest,
    MonitoringConfigListResponse,
    MonitoringConfigSchema,
    MonitoringRunListResponse,
    MonitoringRunSchema,
    MonitoringRunTriggerResponse,
)
from backend.monitoring.service import (
    create_monitoring_config,
    get_latest_monitoring_run,
    get_monitoring_config,
    list_monitoring_configs,
    list_monitoring_runs,
    run_monitoring_job,
)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def _authorize(project_id: str, domain: str, user: CurrentUser, minimum_role: str = "viewer"):
    if domain not in available_domains():
        raise HTTPException(status_code=422, detail=f"Unknown domain '{domain}'. Available: {available_domains()}")
    engine = get_engine()
    project = get_project(engine, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project with id '{project_id}'")
    if project.domain != domain:
        raise HTTPException(status_code=400, detail=f"Project '{project_id}' is a '{project.domain}' project, not '{domain}'")
    membership = get_membership(engine, project.org_id, user.user_id)
    if membership is None or ROLE_RANK[membership.role] < ROLE_RANK[minimum_role]:
        raise HTTPException(status_code=403, detail=f"Requires '{minimum_role}' role or higher in this project's organization")
    return engine


def _get_config_or_404(engine, project_id: str, config_id: str):
    config = get_monitoring_config(engine, project_id, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"No monitoring config '{config_id}' for project '{project_id}'")
    return config


@router.post("/configs", response_model=MonitoringConfigSchema, status_code=201)
def create_config(
    request: MonitoringConfigCreateRequest,
    project_id: str = Query(..., description="The project this monitoring config belongs to."),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringConfigSchema:
    engine = _authorize(project_id, request.domain, user, minimum_role="analyst")
    result = create_monitoring_config(
        engine, project_id, request.domain, request.experiment_id, request.primary_metric,
        request.cadence_seconds, window_hours=request.window_hours, enabled=request.enabled,
    )
    return MonitoringConfigSchema(**result.__dict__)


@router.get("/configs", response_model=MonitoringConfigListResponse)
def list_configs(
    project_id: str = Query(...),
    domain: str = Query(..., description="Used only to authorize this project; a project has one domain."),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringConfigListResponse:
    engine = _authorize(project_id, domain, user)
    results = list_monitoring_configs(engine, project_id)
    return MonitoringConfigListResponse(configs=[MonitoringConfigSchema(**r.__dict__) for r in results])


@router.post("/configs/{config_id}/run-now", response_model=MonitoringRunTriggerResponse, status_code=202)
def trigger_run_now(
    config_id: str,
    background_tasks: BackgroundTasks,
    project_id: str = Query(...),
    domain: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringRunTriggerResponse:
    """Stage 11 task 1: the request never blocks on the Investigation
    engine -- run_monitoring_job (lock acquisition, the actual
    evaluation, and persisting the resulting MonitoringRun row, including
    the duplicate-run check itself) all happen after this response is
    sent. Poll GET .../latest or .../runs to see the outcome."""
    engine = _authorize(project_id, domain, user, minimum_role="analyst")
    config = _get_config_or_404(engine, project_id, config_id)
    background_tasks.add_task(run_monitoring_job, engine, config, get_adapter)
    return MonitoringRunTriggerResponse(config_id=config_id)


@router.get("/configs/{config_id}/runs", response_model=MonitoringRunListResponse)
def get_run_history(
    config_id: str,
    project_id: str = Query(...),
    domain: str = Query(...),
    limit: int = Query(default=20, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringRunListResponse:
    engine = _authorize(project_id, domain, user)
    _get_config_or_404(engine, project_id, config_id)
    results = list_monitoring_runs(engine, project_id, config_id, limit=limit)
    return MonitoringRunListResponse(runs=[MonitoringRunSchema(**r.__dict__) for r in results])


@router.get("/configs/{config_id}/latest", response_model=MonitoringRunSchema)
def get_latest_status(
    config_id: str,
    project_id: str = Query(...),
    domain: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringRunSchema:
    engine = _authorize(project_id, domain, user)
    _get_config_or_404(engine, project_id, config_id)
    latest = get_latest_monitoring_run(engine, project_id, config_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"No monitoring run has ever executed for config '{config_id}'")
    return MonitoringRunSchema(**latest.__dict__)
