"""Stage 6 tasks 3-5: submit/read attribution reviews and the review
queue. Domain-parametrized like backend.app.routers.domains — resolves a
DomainAdapter through backend.app.domain_registry, the only module here
allowed to know about concrete domains.

Stage 7 task 2-4/7: every endpoint requires authentication and resolves a
project-scoped DomainAdapter; submitting a review requires "analyst" role
or higher and is validated against the domain's real registered
mechanisms and real detected attributions (backend.review.service.
submit_review) before anything is written; the review queue prefers
sessions connected to the latest release evaluation's significant
findings over confidence-only ordering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth_deps import ProjectContext, get_project_context, require_role
from backend.app.domain_registry import get_adapter, get_engine
from backend.audit.service import record_audit_event
from backend.app.schemas.review import (
    ReviewQueueItemSchema,
    ReviewQueueResponse,
    ReviewRequest,
    ReviewSchema,
    SessionReviewsResponse,
)
from backend.release.service import get_latest_release_status
from backend.review.service import ReviewValidationError, get_reviews_for_session, list_review_queue, submit_review

router = APIRouter(prefix="/api/v1/domains", tags=["review"])


def _review_to_schema(r) -> ReviewSchema:
    return ReviewSchema(**r.__dict__)


@router.post("/{domain}/sessions/{session_id}/attributions/{failure_mode}/review", response_model=ReviewSchema, status_code=201)
def submit_attribution_review(
    domain: str, session_id: str, failure_mode: str, body: ReviewRequest, ctx: ProjectContext = Depends(require_role("analyst"))
) -> ReviewSchema:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)
    try:
        result = submit_review(
            get_engine(), domain, session_id, failure_mode, decision=body.decision, adapter=adapter,
            corrected_mechanism=body.corrected_mechanism, note=body.note, reviewer=body.reviewer,
            project_id=ctx.project.project_id,
        )
    except ReviewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    record_audit_event(
        get_engine(), action="attribution_review.submit", actor_user_id=ctx.user.user_id, actor_email=ctx.user.email,
        org_id=ctx.project.org_id, project_id=ctx.project.project_id, target=f"{session_id}:{failure_mode}",
        metadata={"domain": domain, "decision": body.decision, "has_corrected_mechanism": body.corrected_mechanism is not None},
    )
    return _review_to_schema(result)


@router.get("/{domain}/sessions/{session_id}/reviews", response_model=SessionReviewsResponse)
def get_session_reviews(domain: str, session_id: str, ctx: ProjectContext = Depends(get_project_context)) -> SessionReviewsResponse:
    reviews_by_mode = get_reviews_for_session(get_engine(), domain, session_id, project_id=ctx.project.project_id)
    return SessionReviewsResponse(domain=domain, session_id=session_id, reviews=[_review_to_schema(r) for r in reviews_by_mode.values()])


@router.get("/{domain}/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    domain: str,
    experiment_id: str | None = None,
    mechanism: str | None = None,
    unreviewed_only: bool = True,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: ProjectContext = Depends(get_project_context),
) -> ReviewQueueResponse:
    adapter = get_adapter(domain, project_id=ctx.project.project_id)

    latest_top_findings = None
    if experiment_id is not None:
        latest = get_latest_release_status(get_engine(), domain, experiment_id, project_id=ctx.project.project_id)
        if latest is not None:
            latest_top_findings = latest.top_findings

    items, total = list_review_queue(
        get_engine(), adapter, domain, experiment_id=experiment_id, mechanism=mechanism,
        unreviewed_only=unreviewed_only, project_id=ctx.project.project_id, latest_top_findings=latest_top_findings,
        limit=limit, offset=offset,
    )
    return ReviewQueueResponse(
        domain=domain,
        items=[
            ReviewQueueItemSchema(
                session_id=i.session_id, experiment_id=i.experiment_id, agent_version=i.agent_version,
                failure_mode=i.failure_mode, detector_source=i.detector_source, confidence=i.confidence,
                evidence_text=i.evidence_text, reviewed=i.review is not None, high_impact=i.high_impact,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
