"""Stage 6 tasks 3-5/7: submit/read attribution reviews, and the review
queue (unreviewed attributions, highest confidence first, filterable by
domain/mechanism/experiment). Reads DomainAdapter.list_reviewable_
attributions() for what exists to review, and its own attribution_reviews
table for what's already been reviewed — never the domain's own
attribution storage directly, and never writes to it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.core.adapter import DomainAdapter
from backend.review.models import AttributionReview

DECISIONS = ("confirmed", "rejected")


@dataclass(frozen=True)
class ReviewResult:
    review_id: str
    domain: str
    session_id: str
    failure_mode: str
    decision: str
    corrected_mechanism: str | None
    note: str | None
    reviewer: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ReviewQueueItem:
    session_id: str
    experiment_id: str
    agent_version: str
    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None
    review: ReviewResult | None  # None means unreviewed


def _row_to_result(row: AttributionReview) -> ReviewResult:
    return ReviewResult(
        review_id=str(row.review_id), domain=row.domain, session_id=row.session_id, failure_mode=row.failure_mode,
        decision=row.decision, corrected_mechanism=row.corrected_mechanism, note=row.note, reviewer=row.reviewer,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def submit_review(
    engine: Engine,
    domain: str,
    session_id: str,
    failure_mode: str,
    decision: str,
    corrected_mechanism: str | None = None,
    note: str | None = None,
    reviewer: str | None = None,
) -> ReviewResult:
    """Upserts on (domain, session_id, failure_mode) — reviewing the same
    attribution again replaces the analyst's decision, it never touches
    (or even reads, here) the original detector row in
    session_failure_attributions."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    review_id = uuid.uuid4()
    with OrmSession(engine) as session:
        stmt = pg_insert(AttributionReview).values(
            review_id=review_id, domain=domain, session_id=session_id, failure_mode=failure_mode,
            decision=decision, corrected_mechanism=corrected_mechanism, note=note, reviewer=reviewer,
            created_at=now, updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain", "session_id", "failure_mode"],
            set_={
                "decision": stmt.excluded.decision,
                "corrected_mechanism": stmt.excluded.corrected_mechanism,
                "note": stmt.excluded.note,
                "reviewer": stmt.excluded.reviewer,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        session.execute(stmt)
        session.commit()

        row = session.execute(
            select(AttributionReview).where(
                AttributionReview.domain == domain, AttributionReview.session_id == session_id, AttributionReview.failure_mode == failure_mode
            )
        ).scalar_one()
        return _row_to_result(row)


def get_reviews_for_session(engine: Engine, domain: str, session_id: str) -> dict[str, ReviewResult]:
    """failure_mode -> its review, only for modes actually reviewed."""
    with OrmSession(engine) as session:
        rows = session.execute(
            select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id == session_id)
        ).scalars().all()
    return {r.failure_mode: _row_to_result(r) for r in rows}


def count_reviews_by_mechanism(engine: Engine, domain: str, session_ids: set[str]) -> dict[str, dict[str, int]]:
    """failure_mode -> {"reviewed": n, "confirmed": n, "rejected": n}, over
    just the given session_ids (a caller scopes this to one experiment's
    sessions) — used by the AI-quality view (Stage 6 task 4) to show
    review coverage alongside, never instead of, the original detector
    prevalence counts."""
    if not session_ids:
        return {}
    with OrmSession(engine) as session:
        rows = session.execute(
            select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id.in_(session_ids))
        ).scalars().all()
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        bucket = counts.setdefault(r.failure_mode, {"reviewed": 0, "confirmed": 0, "rejected": 0})
        bucket["reviewed"] += 1
        bucket[r.decision] += 1
    return counts


def list_review_queue(
    engine: Engine,
    adapter: DomainAdapter,
    domain: str,
    experiment_id: str | None = None,
    mechanism: str | None = None,
    unreviewed_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ReviewQueueItem], int]:
    """Unreviewed, highest-confidence-first (a proxy for "impact" — see
    Stage 6 report). Returns (page, total_matching)."""
    attributions = adapter.list_reviewable_attributions(experiment_id=experiment_id)
    if mechanism is not None:
        attributions = [a for a in attributions if a.failure_mode == mechanism]

    session_ids = {a.session_id for a in attributions}
    reviews_by_key: dict[tuple[str, str], ReviewResult] = {}
    if session_ids:
        with OrmSession(engine) as session:
            rows = session.execute(
                select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id.in_(session_ids))
            ).scalars().all()
        reviews_by_key = {(r.session_id, r.failure_mode): _row_to_result(r) for r in rows}

    items = [
        ReviewQueueItem(
            session_id=a.session_id, experiment_id=a.experiment_id, agent_version=a.agent_version,
            failure_mode=a.failure_mode, detector_source=a.detector_source, confidence=a.confidence,
            evidence_text=a.evidence_text, review=reviews_by_key.get((a.session_id, a.failure_mode)),
        )
        for a in attributions
    ]
    if unreviewed_only:
        items = [i for i in items if i.review is None]

    # Highest confidence first (None confidence sorts last); stable by
    # session_id as a deterministic tiebreaker.
    items.sort(key=lambda i: (-(i.confidence if i.confidence is not None else -1), i.session_id))

    total = len(items)
    return items[offset : offset + limit], total
