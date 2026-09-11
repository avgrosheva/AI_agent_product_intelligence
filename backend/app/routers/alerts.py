"""Stage 6 tasks 1-2: read and acknowledge alerts. Alerts themselves are
created as a side effect of backend.release.service.evaluate_and_persist_
release (see backend.alerts.service.generate_alerts_for_evaluation) — there
is no separate "create alert" endpoint, matching "alert generation is
deterministic, derived from a release evaluation," not a user-authored
event.

Stage 7 tasks 2-3: every endpoint requires authentication and enforces
project-level tenant isolation. The list endpoint takes `project_id`
directly (it has no `domain` path segment to infer one from); the
per-alert endpoints look the alert up first, then check the caller's
membership in ITS project's organization — an alert from a project you
don't belong to 404s exactly like one that doesn't exist, never leaking
which case it was. Acknowledging additionally requires "analyst" or higher.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.alerts.service import AlertResult, acknowledge_alert, get_alert, list_alerts
from backend.app.auth_deps import CurrentUser, ProjectContext, get_current_user, get_engine, get_project_context_by_id
from backend.app.schemas.alerts import AlertListResponse, AlertSchema
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _to_schema(result: AlertResult) -> AlertSchema:
    return AlertSchema(**result.__dict__)


def _authorize_alert(alert: AlertResult, user: CurrentUser, minimum: str) -> None:
    """An alert with no project_id predates Stage 7 tenancy (or was
    generated for ungoverned/legacy data) and is accessible to any
    authenticated user — everything else requires real membership at
    `minimum` role or higher in the owning project's organization.
    Unauthorized access 404s rather than 403s — it never reveals whether
    an alert exists in a project the caller can't see."""
    if alert.project_id is None:
        return
    project = get_project(get_engine(), alert.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="No alert with that id")
    membership = get_membership(get_engine(), project.org_id, user.user_id)
    if membership is None or ROLE_RANK[membership.role] < ROLE_RANK[minimum]:
        raise HTTPException(status_code=404, detail="No alert with that id")


@router.get("", response_model=AlertListResponse)
def list_alerts_endpoint(
    domain: str | None = None,
    experiment_id: str | None = None,
    status: Literal["open", "acknowledged"] | None = None,
    severity: Literal["critical", "warning"] | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(get_project_context_by_id),
) -> AlertListResponse:
    results, total = list_alerts(
        get_engine(), domain=domain, project_id=ctx.project.project_id, experiment_id=experiment_id, status=status, severity=severity,
        limit=limit, offset=offset,
    )
    return AlertListResponse(alerts=[_to_schema(r) for r in results], total=total, limit=limit, offset=offset)


@router.get("/{alert_id}", response_model=AlertSchema)
def get_alert_endpoint(alert_id: str, user: CurrentUser = Depends(get_current_user)) -> AlertSchema:
    result = get_alert(get_engine(), alert_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No alert with id '{alert_id}'")
    _authorize_alert(result, user, "viewer")
    return _to_schema(result)


@router.post("/{alert_id}/acknowledge", response_model=AlertSchema)
def acknowledge_alert_endpoint(alert_id: str, user: CurrentUser = Depends(get_current_user)) -> AlertSchema:
    result = get_alert(get_engine(), alert_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No alert with id '{alert_id}'")
    _authorize_alert(result, user, "analyst")
    updated = acknowledge_alert(get_engine(), alert_id)
    return _to_schema(updated)
