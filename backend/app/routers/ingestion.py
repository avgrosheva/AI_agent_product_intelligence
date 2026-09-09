"""Generic ingestion API (Stage 3). Thin router — validation and
persistence live in backend.ingestion.service, matching this project's
existing "routers are thin" convention (backend/app/main.py's own
docstring).

Stage 7 tasks 1-3: requires authentication, "analyst" role or higher, and
an explicit `project_id` (there is no `domain` path/query segment here to
infer one from — domain is a body field) whose own `domain` must match
the batch's `domain`. project_id is never trusted from the request body
itself — only from this validated, membership-checked query parameter —
so a batch is always stamped with the CALLER's own project, never one
they merely claim.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import get_engine
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project
from backend.ingestion.schemas import IngestBatchRequest, IngestionResponse
from backend.ingestion.service import IngestionValidationError, ingest_batch

router = APIRouter(prefix="/api/v1/ingest", tags=["ingestion"])


@router.post("/sessions", response_model=IngestionResponse, status_code=201)
def ingest_sessions(
    request: IngestBatchRequest,
    project_id: str = Query(..., description="The project to ingest this batch into. Must be a project you belong to, with a matching domain."),
    user: CurrentUser = Depends(get_current_user),
) -> IngestionResponse:
    """Batch-ingest sessions (with their messages/actions/tool calls and
    optional experiments) for any domain. Idempotent by external IDs:
    re-posting the same batch — identical or corrected — converges to the
    same stored state rather than duplicating rows. No commerce-specific
    field is required anywhere in the request body."""
    engine = get_engine()
    project = get_project(engine, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project with id '{project_id}'")
    if project.domain != request.domain:
        raise HTTPException(status_code=400, detail=f"Project '{project_id}' is a '{project.domain}' project, not '{request.domain}'")
    membership = get_membership(engine, project.org_id, user.user_id)
    if membership is None or ROLE_RANK[membership.role] < ROLE_RANK["analyst"]:
        raise HTTPException(status_code=403, detail="Requires 'analyst' role or higher in this project's organization")

    try:
        return ingest_batch(engine, request, project_id=project_id)
    except IngestionValidationError as exc:
        # ErrorResponse.detail is a plain string (shared by every router's
        # error responses) — the structured per-session error list is
        # serialized as JSON text so a caller can still parse it out.
        detail = json.dumps([e.model_dump() for e in exc.errors])
        raise HTTPException(status_code=422, detail=detail) from exc
