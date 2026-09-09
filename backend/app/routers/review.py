"""Stage 6 tasks 3-5: submit/read attribution reviews and the review
queue. Domain-parametrized like backend.app.routers.domains — resolves a
DomainAdapter through backend.app.domain_registry, the only module here
allowed to know about concrete domains.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.domain_registry import get_adapter, get_engine
from backend.app.schemas.review import (
    ReviewQueueItemSchema,
    ReviewQueueResponse,
    ReviewRequest,
    ReviewSchema,
    SessionReviewsResponse,
)
from backend.review.service import get_reviews_for_session, list_review_queue, submit_review

router = APIRouter(prefix="/api/v1/domains", tags=["review"])


def _review_to_schema(r) -> ReviewSchema:
    return ReviewSchema(**r.__dict__)


@router.post("/{domain}/sessions/{session_id}/attributions/{failure_mode}/review", response_model=ReviewSchema, status_code=201)
def submit_attribution_review(domain: str, session_id: str, failure_mode: str, body: ReviewRequest) -> ReviewSchema:
    get_adapter(domain)  # 404s on an unknown domain
    result = submit_review(
        get_engine(), domain, session_id, failure_mode,
        decision=body.decision, corrected_mechanism=body.corrected_mechanism, note=body.note, reviewer=body.reviewer,
    )
    return _review_to_schema(result)


@router.get("/{domain}/sessions/{session_id}/reviews", response_model=SessionReviewsResponse)
def get_session_reviews(domain: str, session_id: str) -> SessionReviewsResponse:
    get_adapter(domain)
    reviews_by_mode = get_reviews_for_session(get_engine(), domain, session_id)
    return SessionReviewsResponse(domain=domain, session_id=session_id, reviews=[_review_to_schema(r) for r in reviews_by_mode.values()])


@router.get("/{domain}/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    domain: str,
    experiment_id: str | None = None,
    mechanism: str | None = None,
    unreviewed_only: bool = True,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReviewQueueResponse:
    adapter = get_adapter(domain)
    items, total = list_review_queue(
        get_engine(), adapter, domain, experiment_id=experiment_id, mechanism=mechanism,
        unreviewed_only=unreviewed_only, limit=limit, offset=offset,
    )
    return ReviewQueueResponse(
        domain=domain,
        items=[
            ReviewQueueItemSchema(
                session_id=i.session_id, experiment_id=i.experiment_id, agent_version=i.agent_version,
                failure_mode=i.failure_mode, detector_source=i.detector_source, confidence=i.confidence,
                evidence_text=i.evidence_text, reviewed=i.review is not None,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
