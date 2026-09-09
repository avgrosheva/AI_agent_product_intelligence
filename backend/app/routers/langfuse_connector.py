"""Langfuse connector API (Stage 9). Mirrors backend.app.routers.ingestion's
own auth pattern exactly (explicit `project_id` query param — there is no
`domain` path segment here to infer one from, since domain is a body
field — "analyst" role or higher) because this endpoint produces and
hands off the exact same IngestBatchRequest shape ingestion itself
accepts: it is a second way to PRODUCE that shape, not a second ingestion
pipeline.

Langfuse API credentials (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY) are
read from this server's own environment only (backend.connectors.langfuse
.config.LangfuseConnectionConfig.from_env) — never accepted as a request
field — so they can never appear in a request log, an audit trail, or a
client-visible error message. `_build_client` is the one seam a test
overrides to inject a fake Langfuse HTTP transport instead of hitting a
real network endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_engine
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project
from backend.connectors.langfuse.client import LangfuseAPIError, LangfuseClient
from backend.connectors.langfuse.config import LangfuseConfigError, LangfuseConnectionConfig
from backend.connectors.langfuse.schemas import LangfuseImportMode, LangfuseImportPreview, LangfuseImportRequest, LangfuseImportResult
from backend.connectors.langfuse.service import ExperimentMappingError, preview_import, run_import
from backend.quality.service import record_connector_run

router = APIRouter(prefix="/api/v1/connectors/langfuse", tags=["connectors"])


def _build_client(host_override: str | None = None) -> LangfuseClient:
    connection = LangfuseConnectionConfig.from_env(host_override=host_override)
    return LangfuseClient(config=connection)


@router.post("/import", response_model=LangfuseImportPreview | LangfuseImportResult)
def import_from_langfuse(
    request: LangfuseImportRequest,
    project_id: str = Query(..., description="The project to import this Langfuse data into. Must be a project you belong to, with a matching domain."),
    user: CurrentUser = Depends(get_current_user),
):
    if request.domain not in available_domains():
        raise HTTPException(status_code=422, detail=f"Unknown domain '{request.domain}'. Available: {available_domains()}")

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
        client = _build_client(request.host)
    except LangfuseConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        if request.mode == LangfuseImportMode.DRY_RUN:
            return preview_import(client, request)
        result = run_import(engine, client, request, project_id=project_id)
        # Stage 11 task 5: the data-quality report's "connector import
        # failures" signal reads only this log -- recorded for `import`
        # mode only, never for a dry_run preview.
        record_connector_run(
            engine, project_id, request.domain, "langfuse", succeeded=True,
            rows_fetched=result.traces_fetched, matched_rows=result.ingestion.sessions_ingested, unmatched_rows=result.sessions_skipped,
        )
        return result
    except LangfuseAPIError as exc:
        if request.mode == LangfuseImportMode.IMPORT:
            record_connector_run(engine, project_id, request.domain, "langfuse", succeeded=False, failure_reason=f"Langfuse API error (status {exc.status_code})")
        # Never forward the raw response body — it's diagnostic detail
        # from an external service, not something to echo back verbatim.
        raise HTTPException(status_code=502, detail=f"Langfuse API error (status {exc.status_code})") from exc
    except ExperimentMappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
