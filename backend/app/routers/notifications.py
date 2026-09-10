"""Notification channel and delivery-log API (Stage 12 tasks 1/3/7).
Same auth pattern as the connectors and monitoring: explicit `project_id`
query param, "analyst" role or higher to create a channel, any member to
read. Which event types are enabled is part of project configuration
(backend.app.routers.domains's config endpoints), not this router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_engine
from backend.app.schemas.notifications import (
    NotificationChannelCreateRequest,
    NotificationChannelListResponse,
    NotificationChannelSchema,
    NotificationDeliveryListResponse,
    NotificationDeliverySchema,
)
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project
from backend.notifications.service import create_channel, list_channels, list_deliveries

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


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


@router.post("/channels", response_model=NotificationChannelSchema, status_code=201)
def create_notification_channel(
    request: NotificationChannelCreateRequest,
    project_id: str = Query(...),
    domain: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> NotificationChannelSchema:
    engine = _authorize(project_id, domain, user, minimum_role="analyst")
    result = create_channel(engine, project_id, request.channel_type, request.url, enabled=request.enabled)
    return NotificationChannelSchema(**result.__dict__)


@router.get("/channels", response_model=NotificationChannelListResponse)
def get_notification_channels(project_id: str = Query(...), domain: str = Query(...), user: CurrentUser = Depends(get_current_user)) -> NotificationChannelListResponse:
    engine = _authorize(project_id, domain, user)
    results = list_channels(engine, project_id)
    return NotificationChannelListResponse(channels=[NotificationChannelSchema(**r.__dict__) for r in results])


@router.get("/deliveries", response_model=NotificationDeliveryListResponse)
def get_notification_deliveries(
    project_id: str = Query(...), domain: str = Query(...), limit: int = Query(default=50, le=200), user: CurrentUser = Depends(get_current_user)
) -> NotificationDeliveryListResponse:
    engine = _authorize(project_id, domain, user)
    results = list_deliveries(engine, project_id, limit=limit)
    return NotificationDeliveryListResponse(deliveries=[NotificationDeliverySchema(**r.__dict__) for r in results])
