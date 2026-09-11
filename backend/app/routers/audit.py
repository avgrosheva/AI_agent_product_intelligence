"""Stage 18 task 3: read-only audit-log API. Requires 'admin' role in the
queried project's organization -- the same authorization discipline
backend.app.routers.auth's own org-member endpoints already use, since an
audit trail is at least as sensitive as a membership list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import get_engine
from backend.app.schemas.audit import AuditLogEntrySchema, AuditLogListResponse
from backend.audit.service import list_audit_events
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project

router = APIRouter(prefix="/api/v1/audit-log", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
def get_audit_log(
    project_id: str = Query(..., description="The project whose audit trail to read -- you must be an admin of its organization."),
    action: str | None = Query(default=None, description="Filter to one action type, e.g. 'project_config.update'."),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
) -> AuditLogListResponse:
    engine = get_engine()
    project = get_project(engine, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project with id '{project_id}'")
    membership = get_membership(engine, project.org_id, user.user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this project's organization")
    if ROLE_RANK[membership.role] < ROLE_RANK["admin"]:
        raise HTTPException(status_code=403, detail=f"Requires role 'admin' or higher; you have '{membership.role}'")

    entries, total = list_audit_events(engine, project_id=project_id, action=action, limit=limit, offset=offset)
    return AuditLogListResponse(
        entries=[
            AuditLogEntrySchema(
                entry_id=e.entry_id, actor_user_id=e.actor_user_id, actor_email=e.actor_email, org_id=e.org_id,
                project_id=e.project_id, action=e.action, target=e.target, created_at=e.created_at, metadata=e.event_metadata,
            )
            for e in entries
        ],
        total=total, limit=limit, offset=offset,
    )
