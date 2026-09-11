"""Stage 6 tasks 3-5/7 + Stage 7 tasks 2/4/7: submit/read attribution
reviews, validate that a review references a real session and a
registered mechanism (never a fake id), and the review queue (unreviewed
attributions connected to significant findings first, then by
confidence — filterable by domain/mechanism/experiment/project). Reads
DomainAdapter.list_reviewable_attributions() for what exists to review,
and its own attribution_reviews table for what's already been reviewed —
never the domain's own attribution storage directly, and never writes to
it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.app.investigation_serialization import values_from_label
from backend.core.adapter import DomainAdapter
from backend.review.models import AttributionReview

DECISIONS = ("confirmed", "rejected")


class ReviewValidationError(Exception):
    """Stage 7 task 4: a review must reference a real session and a
    registered mechanism — raised instead of silently accepting a fake
    id."""


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
    project_id: str | None = None


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
    high_impact: bool = False
    # Stage 19 task 6/8: carried through for both prioritization (is
    # this item on the newest detector/model/prompt version for its
    # mechanism, which has no confirmation-rate track record yet?) and
    # for showing provenance in the UI while reviewing.
    detector_version: str = ""
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    is_newest_version: bool = False


def _row_to_result(row: AttributionReview) -> ReviewResult:
    return ReviewResult(
        review_id=str(row.review_id), domain=row.domain, project_id=row.project_id, session_id=row.session_id, failure_mode=row.failure_mode,
        decision=row.decision, corrected_mechanism=row.corrected_mechanism, note=row.note, reviewer=row.reviewer,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def submit_review(
    engine: Engine,
    domain: str,
    session_id: str,
    failure_mode: str,
    decision: str,
    adapter: DomainAdapter,
    corrected_mechanism: str | None = None,
    note: str | None = None,
    reviewer: str | None = None,
    project_id: str | None = None,
) -> ReviewResult:
    """Upserts on (domain, project_id, session_id, failure_mode) —
    reviewing the same attribution again replaces the analyst's decision,
    it never touches (or even reads, here) the original detector row in
    session_failure_attributions.

    Stage 7 task 4: validates the reference BEFORE writing anything —
    `failure_mode` (and `corrected_mechanism`, if given) must be one of
    this domain's registered mechanisms, and `session_id` must actually
    have a detected instance of `failure_mode` (i.e. appear in
    adapter.list_reviewable_attributions()). Fake/unrelated ids raise
    ReviewValidationError, never silently succeed.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")

    registered_mechanisms = adapter.mechanisms().all_names
    if failure_mode not in registered_mechanisms:
        raise ReviewValidationError(f"'{failure_mode}' is not a registered mechanism for domain '{domain}' (registered: {list(registered_mechanisms)})")
    if corrected_mechanism is not None and corrected_mechanism not in registered_mechanisms:
        raise ReviewValidationError(f"corrected_mechanism '{corrected_mechanism}' is not a registered mechanism for domain '{domain}'")

    matching = adapter.list_reviewable_attributions(session_id=session_id)
    if not any(a.failure_mode == failure_mode for a in matching):
        raise ReviewValidationError(f"no detected '{failure_mode}' attribution found for session '{session_id}' in domain '{domain}'")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    review_id = uuid.uuid4()
    with OrmSession(engine) as session:
        stmt = pg_insert(AttributionReview).values(
            review_id=review_id, domain=domain, project_id=project_id, session_id=session_id, failure_mode=failure_mode,
            decision=decision, corrected_mechanism=corrected_mechanism, note=note, reviewer=reviewer,
            created_at=now, updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain", "project_id", "session_id", "failure_mode"],
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
                AttributionReview.domain == domain, AttributionReview.project_id == project_id,
                AttributionReview.session_id == session_id, AttributionReview.failure_mode == failure_mode,
            )
        ).scalar_one()
        return _row_to_result(row)


def get_reviews_for_session(engine: Engine, domain: str, session_id: str, project_id: str | None = None) -> dict[str, ReviewResult]:
    """failure_mode -> its review, only for modes actually reviewed."""
    with OrmSession(engine) as session:
        stmt = select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id == session_id)
        if project_id is not None:
            stmt = stmt.where(AttributionReview.project_id == project_id)
        rows = session.execute(stmt).scalars().all()
    return {r.failure_mode: _row_to_result(r) for r in rows}


def list_reviews_for_sessions(engine: Engine, domain: str, session_ids: set[str], project_id: str | None = None) -> dict[str, dict[str, ReviewResult]]:
    """session_id -> {failure_mode: its review}, over the given
    session_ids -- the bulk counterpart to get_reviews_for_session, used
    by the generic sessions list (Stage 17 task 3) to filter/annotate a
    page of sessions by review status without one query per row."""
    if not session_ids:
        return {}
    with OrmSession(engine) as session:
        stmt = select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id.in_(session_ids))
        if project_id is not None:
            stmt = stmt.where(AttributionReview.project_id == project_id)
        rows = session.execute(stmt).scalars().all()
    result: dict[str, dict[str, ReviewResult]] = {}
    for r in rows:
        result.setdefault(r.session_id, {})[r.failure_mode] = _row_to_result(r)
    return result


def count_reviews_by_mechanism(engine: Engine, domain: str, session_ids: set[str], project_id: str | None = None) -> dict[str, dict[str, int]]:
    """failure_mode -> {"reviewed": n, "confirmed": n, "rejected": n}, over
    just the given session_ids (a caller scopes this to one experiment's
    sessions) — used by the AI-quality view (Stage 6 task 4) to show
    review coverage alongside, never instead of, the original detector
    prevalence counts."""
    if not session_ids:
        return {}
    with OrmSession(engine) as session:
        stmt = select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id.in_(session_ids))
        if project_id is not None:
            stmt = stmt.where(AttributionReview.project_id == project_id)
        rows = session.execute(stmt).scalars().all()
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        bucket = counts.setdefault(r.failure_mode, {"reviewed": 0, "confirmed": 0, "rejected": 0})
        bucket["reviewed"] += 1
        bucket[r.decision] += 1
    return counts


def _high_impact_session_ids(adapter: DomainAdapter, experiment_id: str | None, top_findings: list[dict]) -> set[str]:
    """Stage 7 task 7: sessions belonging to one of the latest release
    evaluation's top (already BH-corrected + min-effect-filtered)
    segments — reusing the persisted finding list rather than re-running
    the Investigation engine's segment scan a second time."""
    if not top_findings or experiment_id is None:
        return set()
    base_df = adapter.analytics_base_df(experiment_id=experiment_id)
    high_impact: set[str] = set()
    for finding in top_findings:
        label = finding.get("segment_label")
        if not label:
            continue
        dims = [part.split("=", 1)[0] for part in label.split(" & ")]
        values = values_from_label(label)
        if not all(d in base_df.columns for d in dims):
            continue
        mask = pd.Series(True, index=base_df.index)
        for dim, value in zip(dims, values):
            mask &= base_df[dim] == value
        high_impact.update(base_df.loc[mask, "session_id"].astype(str))
    return high_impact


def list_review_queue(
    engine: Engine,
    adapter: DomainAdapter,
    domain: str,
    experiment_id: str | None = None,
    mechanism: str | None = None,
    unreviewed_only: bool = True,
    project_id: str | None = None,
    latest_top_findings: list[dict] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ReviewQueueItem], int]:
    """Stage 19 task 6 (superseding Stage 7 task 7's confidence-only
    tiebreak): ordered by, in priority order —
      1. the item's mechanism's confirmation rate, ascending (mechanisms
         the team is confirming LEAST often need the most review
         attention; a mechanism with too few reviews to have a real rate
         yet is treated as needing MORE review, ranked ahead of every
         mechanism with an established rate — see
         backend.review.quality.QualityCounts.sample_status),
      2. whether the item sits on the newest detector/model/prompt
         version introduced for its mechanism (a fresh version has no
         track record yet and benefits from being reviewed first —
         backend.review.quality.newest_version_per_mechanism),
      3. connected to a significant Investigation finding ("high
         impact" — Stage 7 task 7's original signal, kept, not replaced),
      4. highest detector confidence (None sorts last),
      5. session_id, as a final deterministic tiebreaker.
    Every one of these is computed from data already fetched for this
    same call (the reviewable attributions and their reviews) — no
    additional queries, and the whole chain is one stable sort, so the
    ordering is fully reproducible for the same underlying data.
    `latest_top_findings` is the calling router's already-fetched latest
    release evaluation's top_findings (or None if no evaluation has run
    yet / no experiment_id given)."""
    from backend.review.quality import compute_attribution_quality, newest_version_per_mechanism

    attributions = adapter.list_reviewable_attributions(experiment_id=experiment_id)
    if mechanism is not None:
        attributions = [a for a in attributions if a.failure_mode == mechanism]

    high_impact_ids = _high_impact_session_ids(adapter, experiment_id, latest_top_findings or [])

    session_ids = {a.session_id for a in attributions}
    reviews_by_key: dict[tuple[str, str], ReviewResult] = {}
    if session_ids:
        with OrmSession(engine) as session:
            stmt = select(AttributionReview).where(AttributionReview.domain == domain, AttributionReview.session_id.in_(session_ids))
            if project_id is not None:
                stmt = stmt.where(AttributionReview.project_id == project_id)
            rows = session.execute(stmt).scalars().all()
        reviews_by_key = {(r.session_id, r.failure_mode): _row_to_result(r) for r in rows}

    quality = compute_attribution_quality(attributions, reviews_by_key)
    # A mechanism with too few reviews to have a real confirmation rate
    # (sample_status == "insufficient_review_data") is ranked as if its
    # rate were below every ACTUAL rate (which is >= 0.0) -- -1.0 always
    # sorts first ascending, prioritizing it for more review.
    confirmation_rate_by_mechanism = {
        m.failure_mode: (m.counts.confirmation_rate if m.counts.sample_status == "enough_data" else -1.0) for m in quality.by_mechanism
    }
    newest_version = newest_version_per_mechanism(attributions)

    items = [
        ReviewQueueItem(
            session_id=a.session_id, experiment_id=a.experiment_id, agent_version=a.agent_version,
            failure_mode=a.failure_mode, detector_source=a.detector_source, confidence=a.confidence,
            evidence_text=a.evidence_text, review=reviews_by_key.get((a.session_id, a.failure_mode)),
            high_impact=a.session_id in high_impact_ids,
            detector_version=a.detector_version, provider=a.provider, model=a.model, prompt_version=a.prompt_version,
            is_newest_version=newest_version.get(a.failure_mode) == (a.detector_version, a.provider or "", a.model or "", a.prompt_version or ""),
        )
        for a in attributions
    ]
    if unreviewed_only:
        items = [i for i in items if i.review is None]

    items.sort(
        key=lambda i: (
            confirmation_rate_by_mechanism.get(i.failure_mode, -1.0),
            not i.is_newest_version,
            not i.high_impact,
            -(i.confidence if i.confidence is not None else -1),
            i.session_id,
        )
    )

    total = len(items)
    return items[offset : offset + limit], total
