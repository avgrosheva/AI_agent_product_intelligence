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
        return run_enrichment(engine, client, project_id, request)
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JoinConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PostgresConnectorError as exc:
        raise HTTPException(status_code=502, detail="Business Postgres source is unreachable") from exc
