"""Stage 18 task 3/11: privileged actions are recorded to an append-only
audit log, and reading that log back is admin-only. Uses its own
dedicated org/project (never api_client's default admin identity for the
role-boundary assertions) — same pattern tests/test_rbac.py already
established for exercising role permissions through the real HTTP API
with separately-issued tokens."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.db import get_database_url
from backend.app.main import app
from backend.auth.security import create_access_token
from backend.auth.service import add_member, create_organization, create_project, register_user


def _engine():
    return create_engine(get_database_url())


def _new_user(email_prefix: str) -> tuple[str, str]:
    email = f"{email_prefix}-{uuid.uuid4()}@example.com"
    user = register_user(_engine(), email, "password123")
    return user.user_id, email


def _client_for(user_id: str) -> TestClient:
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(user_id)}"
    return client


@pytest.fixture(scope="module")
def audit_org(db_engine):
    # `db_engine` (unused directly) is the dependency that actually
    # matters here: its session-scoped setup is what runs `alembic
    # upgrade head` against the test database before anything else
    # touches it. This fixture talks to the database directly via its own
    # `_engine()` rather than through `db_engine`/`classified_engine`/
    # `test_identity` (it needs a fresh org, not the shared demo-dataset
    # one those fixtures build), so without this parameter pytest could
    # run this fixture's setup BEFORE the migration that creates
    # audit_log_entries -- exactly what happened the first time this file
    # ran, "relation audit_log_entries does not exist" on every test
    # whose fixture chain didn't happen to pull in db_engine some other
    # way first.
    admin_user_id, admin_email = _new_user("audit-admin")
    org = create_organization(_engine(), "Audit Log Test Org", admin_user_id)
    project = create_project(_engine(), org.org_id, "Audit Log Support Project", "support")

    analyst_user_id, analyst_email = _new_user("audit-analyst")
    add_member(_engine(), org.org_id, analyst_email, "analyst")

    outsider_user_id, _ = _new_user("audit-outsider")

    return {
        "org_id": org.org_id,
        "project_id": project.project_id,
        "admin_client": _client_for(admin_user_id),
        "analyst_client": _client_for(analyst_user_id),
        "outsider_client": _client_for(outsider_user_id),
    }


def test_updating_project_config_is_recorded_with_changed_field_names_not_values(audit_org):
    project_id = audit_org["project_id"]
    resp = audit_org["analyst_client"].put(
        f"/api/v1/domains/support/config?project_id={project_id}",
        json={"primary_metric": "resolution_rate"},
    )
    assert resp.status_code == 200

    log = audit_org["admin_client"].get(f"/api/v1/audit-log?project_id={project_id}&action=project_config.update").json()
    assert log["total"] >= 1
    entry = log["entries"][0]
    assert entry["action"] == "project_config.update"
    assert entry["project_id"] == project_id
    assert entry["org_id"] == audit_org["org_id"]
    assert entry["target"] == "support"
    assert entry["metadata"]["changed_fields"] == ["primary_metric"]
    # The metadata is field NAMES, never the config's own content.
    assert "resolution_rate" not in str(entry["metadata"])


def test_attribution_review_submission_is_recorded(api_client, db_engine, commerce_project_id):
    """Commerce, not audit_org's own (support) project: a reviewable
    attribution needs a real session_failure_attributions row, which is
    commerce-only storage (foreign-keyed to `sessions`, not the generic
    `ingested_sessions` the support domain uses) — the dev-scale commerce
    fixture db_engine already loaded has plenty of real detected=true
    rows to use, matching tests/test_attribution_review.py's own
    approach. api_client is test_identity's admin, already a member of
    the org that owns commerce_project_id."""
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sfa.session_id::text AS session_id, sfa.failure_mode::text AS failure_mode FROM session_failure_attributions sfa "
                "LEFT JOIN attribution_reviews ar ON ar.session_id = sfa.session_id::text AND ar.failure_mode::text = sfa.failure_mode::text AND ar.domain = 'commerce' "
                "WHERE sfa.detected = true AND ar.session_id IS NULL ORDER BY sfa.session_id, sfa.failure_mode LIMIT 1"
            )
        ).mappings().first()
    assert row is not None, "expected at least one detected, never-reviewed commerce attribution in the dev-scale fixture"
    session_id, failure_mode = row["session_id"], row["failure_mode"]

    review_resp = api_client.post(
        f"/api/v1/domains/commerce/sessions/{session_id}/attributions/{failure_mode}/review",
        json={"decision": "confirmed", "note": "looks right"},
    )
    assert review_resp.status_code == 201

    log = api_client.get(f"/api/v1/audit-log?project_id={commerce_project_id}&action=attribution_review.submit").json()
    assert log["total"] >= 1
    entry = next(e for e in log["entries"] if e["target"] == f"{session_id}:{failure_mode}")
    assert entry["metadata"]["decision"] == "confirmed"
    assert entry["project_id"] == commerce_project_id


def test_reading_the_audit_log_requires_admin_role(audit_org):
    project_id = audit_org["project_id"]

    analyst_resp = audit_org["analyst_client"].get(f"/api/v1/audit-log?project_id={project_id}")
    assert analyst_resp.status_code == 403

    outsider_resp = audit_org["outsider_client"].get(f"/api/v1/audit-log?project_id={project_id}")
    assert outsider_resp.status_code == 403

    admin_resp = audit_org["admin_client"].get(f"/api/v1/audit-log?project_id={project_id}")
    assert admin_resp.status_code == 200
    body = admin_resp.json()
    assert "total" in body and "limit" in body and "offset" in body


def test_audit_log_is_scoped_to_the_requested_project_only(audit_org, support_project_id):
    """A project this org's admin has nothing to do with must never leak
    into (or be readable via) this org's audit-log query."""
    project_id = audit_org["project_id"]
    log = audit_org["admin_client"].get(f"/api/v1/audit-log?project_id={project_id}").json()
    assert all(e["project_id"] == project_id for e in log["entries"])

    # And the reverse: this org's admin has no access to a DIFFERENT
    # project's audit log at all.
    other_resp = audit_org["admin_client"].get(f"/api/v1/audit-log?project_id={support_project_id}")
    assert other_resp.status_code == 403
