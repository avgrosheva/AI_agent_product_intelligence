"""Generic ingestion API (Stage 3). Thin router — validation and
persistence live in backend.ingestion.service, matching this project's
existing "routers are thin" convention (backend/app/main.py's own
docstring).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from backend.app.dependencies import get_engine
from backend.ingestion.schemas import IngestBatchRequest, IngestionResponse
from backend.ingestion.service import IngestionValidationError, ingest_batch

router = APIRouter(prefix="/api/v1/ingest", tags=["ingestion"])


@router.post("/sessions", response_model=IngestionResponse, status_code=201)
def ingest_sessions(request: IngestBatchRequest) -> IngestionResponse:
    """Batch-ingest sessions (with their messages/actions/tool calls and
    optional experiments) for any domain. Idempotent by external IDs:
    re-posting the same batch — identical or corrected — converges to the
    same stored state rather than duplicating rows. No commerce-specific
    field is required anywhere in the request body."""
    try:
        return ingest_batch(get_engine(), request)
    except IngestionValidationError as exc:
        # ErrorResponse.detail is a plain string (shared by every router's
        # error responses) — the structured per-session error list is
        # serialized as JSON text so a caller can still parse it out.
        detail = json.dumps([e.model_dump() for e in exc.errors])
        raise HTTPException(status_code=422, detail=detail) from exc
