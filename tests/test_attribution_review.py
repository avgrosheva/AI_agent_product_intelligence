"""Stage 6 tasks 3-5/7: human review of failure attributions — submit
confirm/reject/correct/note decisions, prove the original detector output
is never modified, and prove the review queue orders/filters correctly
for both domains."""

from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module", autouse=True)
def _clean_attribution_reviews_table(db_engine):
    """attribution_reviews has no FK to sessions (deliberately, to stay
    domain-agnostic — see backend/review/models.py) so it is NOT wiped by
    conftest.py's dev-dataset truncate-and-reload. Without this, the
    index-based "pick a fresh, never-reviewed attribution" helper below
    would see stale reviews left over from a previous `pytest` invocation
    against the same persistent test database."""
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM attribution_reviews"))
    yield


def _one_detected_commerce_attribution(db_engine, index: int = 0):
    """Deterministically ordered so each test can request a DISTINCT row
    (via `index`) — the test database persists across the whole pytest
    session, so two tests reviewing "the first detected=true row" would
    otherwise silently collide and see each other's review."""
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT session_id::text AS session_id, failure_mode::text AS failure_mode FROM session_failure_attributions "
                "WHERE detected = true ORDER BY session_id, failure_mode LIMIT 1 OFFSET :offset"
            ),
            {"offset": index},
        ).mappings().all()
    assert rows, f"expected the dev-scale fixture to have at least {index + 1} detected=true attribution(s)"
    return rows[0]["session_id"], rows[0]["failure_mode"]


def test_submit_confirm_review(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=0)
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "confirmed", "note": "looks right"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "commerce"
    assert body["session_id"] == session_id
    assert body["failure_mode"] == failure_mode
    assert body["decision"] == "confirmed"
    assert body["note"] == "looks right"
    assert body["corrected_mechanism"] is None


def test_submit_reject_review_with_corrected_mechanism(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=1)
    other_mode = "poor_ranking" if failure_mode != "poor_ranking" else "retrieval_failure"
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "rejected", "corrected_mechanism": other_mode, "note": "actually a different mechanism", "reviewer": "analyst-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["decision"] == "rejected"
    assert body["corrected_mechanism"] == other_mode
    assert body["reviewer"] == "analyst-1"


def test_reviewing_again_updates_the_same_review_not_a_new_row(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=2)
    first = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review", json={"decision": "confirmed"}
    ).json()
    second = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "rejected", "note": "changed my mind"},
    ).json()
    assert first["review_id"] == second["review_id"]
    assert second["decision"] == "rejected"
    assert second["note"] == "changed my mind"

    listing = api_client.get(f"/api/v1/domains/commerce/sessions/{session_id}/reviews").json()
    matching = [r for r in listing["reviews"] if r["failure_mode"] == failure_mode]
    assert len(matching) == 1  # not two


def test_original_attribution_is_never_modified_by_a_review(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=3)

    def _snapshot():
        with db_engine.connect() as conn:
            return dict(
                conn.execute(
                    text(
                        "SELECT detected, detector_source::text AS detector_source, confidence, evidence_text "
                        "FROM session_failure_attributions WHERE session_id = :sid AND failure_mode = :failure_mode"
                    ),
                    {"sid": session_id, "failure_mode": failure_mode},
                ).mappings().first()
            )

    before = _snapshot()
    api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "rejected", "corrected_mechanism": "wrong_tool_selection", "note": "definitely wrong"},
    )
    after = _snapshot()
    assert before == after


def test_session_detail_surfaces_review_status_without_touching_original_fields(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=4)
    detail_before = api_client.get(f"/api/v1/domains/commerce/sessions/{session_id}").json()
    original = next(f for f in detail_before["failure_attributions"] if f["failure_mode"] == failure_mode)
    assert original["review_status"] == "unreviewed"
    original_confidence = original["confidence"]
    original_evidence = original["evidence_text"]

    api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "confirmed", "note": "yep"},
    )

    detail_after = api_client.get(f"/api/v1/domains/commerce/sessions/{session_id}").json()
    reviewed = next(f for f in detail_after["failure_attributions"] if f["failure_mode"] == failure_mode)
    assert reviewed["review_status"] == "confirmed"
    assert reviewed["review_note"] == "yep"
    # the original detector fields are byte-identical to before the review
    assert reviewed["confidence"] == original_confidence
    assert reviewed["evidence_text"] == original_evidence


def test_generic_session_detail_also_surfaces_review_status(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=5)
    api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review", json={"decision": "confirmed"}
    )
    detail = api_client.get(f"/api/v1/domains/commerce/sessions/{session_id}").json()
    matching = [f for f in detail["failure_attributions"] if f["failure_mode"] == failure_mode]
    assert len(matching) == 1
    assert matching[0]["review_status"] == "confirmed"


def test_review_queue_is_ordered_by_confidence_descending(api_client, db_engine):
    resp = api_client.get("/api/v1/domains/commerce/review-queue?unreviewed_only=false&limit=200")
    assert resp.status_code == 200
    items = resp.json()["items"]
    confidences = [i["confidence"] for i in items if i["confidence"] is not None]
    assert confidences == sorted(confidences, reverse=True)


def test_review_queue_unreviewed_only_excludes_reviewed_sessions(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=6)
    api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review", json={"decision": "confirmed"}
    )
    resp = api_client.get("/api/v1/domains/commerce/review-queue?unreviewed_only=true&limit=200")
    items = resp.json()["items"]
    assert not any(i["session_id"] == session_id and i["failure_mode"] == failure_mode for i in items)


def test_review_queue_filters_by_mechanism(api_client, db_engine):
    _, failure_mode = _one_detected_commerce_attribution(db_engine)
    resp = api_client.get(f"/api/v1/domains/commerce/review-queue?mechanism={failure_mode}&unreviewed_only=false&limit=200")
    items = resp.json()["items"]
    assert len(items) > 0
    assert all(i["failure_mode"] == failure_mode for i in items)


def test_review_queue_filters_by_experiment_id(api_client, experiment_id):
    resp = api_client.get(f"/api/v1/domains/commerce/review-queue?experiment_id={experiment_id}&unreviewed_only=false&limit=200")
    items = resp.json()["items"]
    assert all(i["experiment_id"] == experiment_id for i in items)


def test_support_domain_review_queue_is_empty_no_mechanisms_registered(api_client):
    resp = api_client.get("/api/v1/domains/support/review-queue?unreviewed_only=false")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_review_submission_is_domain_parametrized_and_still_validated_for_support():
    """Compatibility (task 7): the review API itself is domain-parametrized
    (it never assumes commerce's storage) — but Stage 7 task 4's reference
    validation applies uniformly, so a support-domain review (support has
    zero registered mechanisms — Stage 3 task 7) correctly REJECTS any
    mechanism name, rather than silently accepting a fake one the way a
    domain-specific shortcut might."""
    from sqlalchemy import create_engine

    from backend.app.db import get_database_url
    from backend.domains.support.adapter import SupportAdapter
    from backend.review.service import ReviewValidationError, submit_review

    engine = create_engine(get_database_url())
    adapter = SupportAdapter(engine)
    with pytest.raises(ReviewValidationError):
        submit_review(engine, "support", "some-support-session-id", "hypothetical_mode", decision="confirmed", adapter=adapter, note="test")


def test_submit_review_rejects_invalid_decision(api_client, db_engine):
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine)
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review", json={"decision": "maybe"}
    )
    assert resp.status_code == 422


def test_submit_review_rejects_unregistered_mechanism(api_client, db_engine):
    """Stage 7 task 4: failure_mode must be one of the domain's registered
    mechanisms — a made-up name is rejected, not silently stored."""
    session_id, _ = _one_detected_commerce_attribution(db_engine, index=7)
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/not_a_real_mechanism/review",
        json={"decision": "confirmed"},
    )
    assert resp.status_code == 422


def test_submit_review_rejects_fake_session_id(api_client, db_engine):
    """Stage 7 task 4: even a registered mechanism name must actually have
    been DETECTED for the given session — a session that never had this
    mechanism fire (or a session that doesn't exist) is rejected."""
    _, failure_mode = _one_detected_commerce_attribution(db_engine, index=8)
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/00000000-0000-0000-0000-000000000000/attributions/{failure_mode}/review",
        json={"decision": "confirmed"},
    )
    assert resp.status_code == 422


def test_submit_review_rejects_unregistered_corrected_mechanism(api_client, db_engine):
    """Stage 7 task 4: corrected_mechanism, when given, must also be a
    registered mechanism — not an arbitrary string."""
    session_id, failure_mode = _one_detected_commerce_attribution(db_engine, index=9)
    resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "rejected", "corrected_mechanism": "not_a_real_mechanism_either"},
    )
    assert resp.status_code == 422
