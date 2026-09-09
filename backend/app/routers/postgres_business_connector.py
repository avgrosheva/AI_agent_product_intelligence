"""Postgres business-data connector API (Stage 10). Same auth pattern as
ingestion and the Langfuse connector: explicit `project_id` query param
(no `domain` path segment — domain is a body field), "analyst" role or
higher. Business database credentials (BUSINESS_DB_*) are read from this
server's own environment only — never accepted as a request field.
`_build_client` is the one seam a test overrides to inject a fake/real
test Postgres instead of a production customer database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_engine
from backend.auth.models import ROLE_RANK
from backend.auth.service import get_membership, get_project
from backend.connectors.postgres_business.client import PostgresBusinessClient, PostgresConnectorError, UnsafeQueryError
from backend.connectors.postgres_business.config import PostgresConfigError, PostgresConnectionConfig
from backend.connectors.postgres_business.schemas import PostgresEnrichmentMode, PostgresEnrichmentPreview, PostgresEnrichmentRequest, PostgresEnrichmentResult
from backend.connectors.postgres_business.service import JoinConfigError, preview_enrichment, run_enrichment
from backend.quality.service import record_connector_run

router = APIRouter(prefix="/api/v1/connectors/postgres-business", tags=["connectors"])


def _build_client() -> PostgresBusinessClient:
    connection = PostgresConnectionConfig.from_env()
    return PostgresBusinessClient(config=connection)


@router.post("/enrich", response_model=PostgresEnrichmentPreview | PostgresEnrichmentResult)
def enrich_from_postgres(
    request: PostgresEnrichmentRequest,
    project_id: str = Query(..., description="The project whose sessions this business data enriches. Must be a project you belong to, with a matching domain."),
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
        client = _build_client()
    except PostgresConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        if request.mode == PostgresEnrichmentMode.DRY_RUN:
            return preview_enrichment(engine, client, project_id, request)
        result = run_enrichment(engine, client, project_id, request)
        # Stage 11 task 5: the data-quality report's "unmatched business-
        # data rate", "duplicate/conflicting data rate", and "connector
        # import failures" signals read only this log -- recorded for
        # `import` mode only, never for a dry_run preview.
        record_connector_run(
            engine, project_id, request.domain, "postgres_business", succeeded=True,
            rows_fetched=result.source_rows_fetched, matched_rows=result.matched_rows,
            unmatched_rows=len(result.unmatched_source_rows), validation_error_count=len(result.validation_errors),
        )
        return result
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JoinConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PostgresConnectorError as exc:
        if request.mode == PostgresEnrichmentMode.IMPORT:
            record_connector_run(engine, project_id, request.domain, "postgres_business", succeeded=False, failure_reason=str(exc))
        raise HTTPException(status_code=502, detail="Business Postgres source is unreachable") from exc
