"""Stage 19 task 6/11: backend.review.service.list_review_queue's new
quality-based prioritization (superseding Stage 7 task 7's
confidence-only tiebreak). Uses a small stub DomainAdapter so every
signal (mechanism confirmation rate, "newest version", high-impact) can
be fully controlled and independently verified -- the real commerce dev
fixture doesn't give a test control over confirmation rates or multiple
detector versions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from backend.core.attribution import Mechanism, MechanismRegistry, ReviewableAttribution
from backend.review.service import list_review_queue, submit_review


class _StubAdapter:
    domain = "commerce"

    def __init__(self, attributions: list[ReviewableAttribution]):
        self._attributions = attributions

    def list_reviewable_attributions(self, experiment_id: str | None = None, session_id: str | None = None) -> list[ReviewableAttribution]:
        items = self._attributions
        if experiment_id is not None:
            items = [a for a in items if a.experiment_id == experiment_id]
        if session_id is not None:
            items = [a for a in items if a.session_id == session_id]
        return items

    def mechanisms(self) -> MechanismRegistry:
        return MechanismRegistry([
            Mechanism(name="low_confirm_mode", source="semantic"),
            Mechanism(name="high_confirm_mode", source="semantic"),
            Mechanism(name="unreviewed_mode", source="deterministic"),
        ])


def _attribution(sid: str, mode: str, confidence: float, version="v1", created="2026-01-01T00:00:00") -> ReviewableAttribution:
    return ReviewableAttribution(
        session_id=sid, experiment_id="exp-priority-test", agent_version="v2", failure_mode=mode, detector_source="semantic",
        confidence=confidence, evidence_text="e", detector_version=version, provider=None, model=None, prompt_version=None,
        created_at=datetime.fromisoformat(created),
    )


@pytest.fixture
def project_id(db_engine) -> str:
    # `db_engine` (unused directly): forces the alembic-migrated,
    # dev-dataset-loaded test database to exist before attribution_reviews
    # is touched -- same reasoning as tests/test_audit_log.py's audit_org
    # fixture.
    return f"priority-test-project-{uuid.uuid4().hex[:8]}"


def test_a_mechanism_with_a_low_confirmation_rate_is_prioritized_over_one_with_a_high_rate(db_engine, project_id):
    domain = "commerce"
    # 10 reviews each -- enough to clear MIN_REVIEWS_FOR_QUALITY_CLAIM, so
    # this is a real, established rate difference, not noise.
    low_ids = [f"low-{i}" for i in range(10)]
    high_ids = [f"high-{i}" for i in range(10)]
    attributions = [_attribution(sid, "low_confirm_mode", confidence=0.5) for sid in low_ids] + [
        _attribution(sid, "high_confirm_mode", confidence=0.5) for sid in high_ids
    ]
    adapter = _StubAdapter(attributions)

    # low_confirm_mode: 2/10 confirmed (0.2). high_confirm_mode: 9/10 confirmed (0.9).
    for i, sid in enumerate(low_ids):
        submit_review(db_engine, domain, sid, "low_confirm_mode", "confirmed" if i < 2 else "rejected", adapter, project_id=project_id)
    for i, sid in enumerate(high_ids):
        submit_review(db_engine, domain, sid, "high_confirm_mode", "confirmed" if i < 9 else "rejected", adapter, project_id=project_id)

    items, total = list_review_queue(db_engine, adapter, domain, unreviewed_only=False, project_id=project_id, limit=200)
    assert total == 20
    # Every low_confirm_mode item outranks every high_confirm_mode item.
    modes_in_order = [i.failure_mode for i in items]
    last_low_index = max(idx for idx, m in enumerate(modes_in_order) if m == "low_confirm_mode")
    first_high_index = min(idx for idx, m in enumerate(modes_in_order) if m == "high_confirm_mode")
    assert last_low_index < first_high_index


def test_a_mechanism_with_too_few_reviews_to_have_a_real_rate_is_prioritized_like_a_low_confirmation_rate(db_engine, project_id):
    domain = "commerce"
    # high_confirm_mode gets 10 reviews (enough_data, high rate).
    # unreviewed_mode gets attributions but ZERO reviews at all --
    # insufficient_review_data, which must rank as if it needed review
    # MORE, not less, than an established-but-imperfect rate.
    high_ids = [f"high-{i}" for i in range(10)]
    sparse_ids = [f"sparse-{i}" for i in range(3)]
    attributions = [_attribution(sid, "high_confirm_mode", confidence=0.5) for sid in high_ids] + [
        _attribution(sid, "unreviewed_mode", confidence=0.5) for sid in sparse_ids
    ]
    adapter = _StubAdapter(attributions)
    for i, sid in enumerate(high_ids):
        submit_review(db_engine, domain, sid, "high_confirm_mode", "confirmed" if i < 9 else "rejected", adapter, project_id=project_id)
    # unreviewed_mode: leave entirely unreviewed.

    items, total = list_review_queue(db_engine, adapter, domain, unreviewed_only=True, project_id=project_id, limit=200)
    assert total == 3  # only unreviewed_mode's 3 items are unreviewed
    assert all(i.failure_mode == "unreviewed_mode" for i in items)


def test_an_item_on_the_newest_detector_version_for_its_mechanism_is_prioritized_over_an_older_version(db_engine, project_id):
    domain = "commerce"
    # Same mechanism, same (insufficient) confirmation-rate bucket for
    # both -- version recency is the ONLY signal that should differ.
    attributions = [
        _attribution("old-1", "low_confirm_mode", confidence=0.9, version="v1", created="2026-01-01T00:00:00"),
        _attribution("new-1", "low_confirm_mode", confidence=0.1, version="v2", created="2026-02-01T00:00:00"),
    ]
    adapter = _StubAdapter(attributions)

    items, _ = list_review_queue(db_engine, adapter, domain, unreviewed_only=True, project_id=project_id, limit=200)
    # v2 (newer) comes first even though its confidence (0.1) is far
    # lower than v1's (0.9) -- version recency outranks confidence.
    assert items[0].session_id == "new-1"
    assert items[1].session_id == "old-1"


def test_ordering_is_a_deterministic_function_of_the_same_underlying_data_called_twice(db_engine, project_id):
    domain = "commerce"
    attributions = [_attribution(f"s{i}", "unreviewed_mode", confidence=float(i) / 10) for i in range(15)]
    adapter = _StubAdapter(attributions)

    items_a, _ = list_review_queue(db_engine, adapter, domain, unreviewed_only=True, project_id=project_id, limit=200)
    items_b, _ = list_review_queue(db_engine, adapter, domain, unreviewed_only=True, project_id=project_id, limit=200)
    assert [i.session_id for i in items_a] == [i.session_id for i in items_b]
    # Within one mechanism, same version, no reviews yet at all: falls
    # through to confidence descending, then session_id.
    assert [i.session_id for i in items_a] == [f"s{i}" for i in range(14, -1, -1)]


def test_review_based_quality_signals_do_not_cross_project_boundaries(db_engine):
    """Tenant isolation for the new quality-based prioritization signal
    (task 6) and, by extension, backend.review.quality's use of
    list_reviews_for_sessions (also what
    backend.app.routers.domains._human_review_quality_report calls for
    task 5's frontend section) -- two projects reviewing the exact SAME
    (session_id, failure_mode) attributions must never see each other's
    decisions, even though attribution_reviews' uniqueness constraint is
    keyed on (domain, project_id, session_id, failure_mode), which would
    happily let a bug silently overwrite project A's review with project
    B's if project_id were ever dropped from a lookup."""
    domain = "commerce"
    project_a = f"priority-test-project-{uuid.uuid4().hex[:8]}"
    project_b = f"priority-test-project-{uuid.uuid4().hex[:8]}"
    ids = [f"shared-{i}" for i in range(10)]
    attributions = [_attribution(sid, "low_confirm_mode", confidence=0.5) for sid in ids]
    adapter = _StubAdapter(attributions)

    # Project A confirms almost everything (high confirmation rate).
    # Project B, reviewing the IDENTICAL attributions, rejects almost
    # everything (low confirmation rate).
    for i, sid in enumerate(ids):
        submit_review(db_engine, domain, sid, "low_confirm_mode", "confirmed" if i < 9 else "rejected", adapter, project_id=project_a)
    for i, sid in enumerate(ids):
        submit_review(db_engine, domain, sid, "low_confirm_mode", "confirmed" if i < 1 else "rejected", adapter, project_id=project_b)

    items_a, _ = list_review_queue(db_engine, adapter, domain, unreviewed_only=False, project_id=project_a, limit=200)
    items_b, _ = list_review_queue(db_engine, adapter, domain, unreviewed_only=False, project_id=project_b, limit=200)

    # Same mechanism, same attributions -- but each project's queue must
    # reflect only ITS OWN reviews. Project A confirmed sessions 0-8 and
    # rejected session 9; project B confirmed only session 0 and
    # rejected the rest. If review data leaked across projects (e.g. a
    # lookup that dropped project_id), both queues would show the same
    # decisions for every session.
    decisions_a = {i.session_id: (i.review.decision if i.review else None) for i in items_a}
    decisions_b = {i.session_id: (i.review.decision if i.review else None) for i in items_b}
    assert all(decisions_a[sid] == "confirmed" for sid in ids[:9])
    assert decisions_a[ids[9]] == "rejected"
    assert decisions_b[ids[0]] == "confirmed"
    assert all(decisions_b[sid] == "rejected" for sid in ids[1:])
