"""Stage 6 tasks 1-2: read and acknowledge alerts. Alerts themselves are
created as a side effect of backend.release.service.evaluate_and_persist_
release (see backend.alerts.service.generate_alerts_for_evaluation) — there
is no separate "create alert" endpoint, matching "alert generation is
deterministic, derived from a release evaluation," not a user-authored
event.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from backend.alerts.service import acknowledge_alert, get_alert, list_alerts
from backend.app.domain_registry import get_engine
from backend.app.schemas.alerts import AlertListResponse, AlertSchema

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _to_schema(result) -> AlertSchema:
    return AlertSchema(**result.__dict__)


@router.get("", response_model=AlertListResponse)
def list_alerts_endpoint(
    domain: str | None = None,
    experiment_id: str | None = None,
    status: Literal["open", "acknowledged"] | None = None,
    severity: Literal["critical", "warning"] | None = None,
    limit: int = Query(default=50, le=200),
) -> AlertListResponse:
    results = list_alerts(get_engine(), domain=domain, experiment_id=experiment_id, status=status, severity=severity, limit=limit)
    return AlertListResponse(alerts=[_to_schema(r) for r in results])


@router.get("/{alert_id}", response_model=AlertSchema)
def get_alert_endpoint(alert_id: str) -> AlertSchema:
    result = get_alert(get_engine(), alert_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No alert with id '{alert_id}'")
    return _to_schema(result)


@router.post("/{alert_id}/acknowledge", response_model=AlertSchema)
def acknowledge_alert_endpoint(alert_id: str) -> AlertSchema:
    result = acknowledge_alert(get_engine(), alert_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No alert with id '{alert_id}'")
    return _to_schema(result)
