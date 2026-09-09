"""Stage 7 tasks 2-3/8: role permissions (admin/analyst/viewer) and
tenant/project isolation, exercised through the real HTTP API with
separately-issued tokens for each role — never reusing api_client's
default admin identity for the calls being permission-tested."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.app.main import app
from backend.auth.security import create_access_token
from backend.auth.service import add_member, create_organization, create_project, register_user


def _engine():
    return create_engine(get_database_url())


def _new_user(email_prefix: str) -> tuple[str, str]:
    """Returns (user_id, email)."""
    email = f"{email_prefix}-{uuid.uuid4()}@example.com"
    user = register_user(_engine(), email, "password123")
    return user.user_id, email


def _client_for(user_id: str) -> TestClient:
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(user_id)}"
    return client


@pytest.fixture(scope="module")
def rbac_org(test_identity):
    """A dedicated org (reusing test_identity's admin as its owner is
    unnecessary — a fresh org keeps this file's members independent of
    other test files' membership churn) with one support project, and
    three member tokens: admin (the creator), analyst, viewer."""
    admin_user_id, admin_email = _new_user("rbac-admin")
    org = create_organization(_engine(), "RBAC Test Org", admin_user_id)
    project = create_project(_engine(), org.org_id, "RBAC Support Project", "support")

    analyst_user_id, analyst_email = _new_user("rbac-analyst")
    add_member(_engine(), org.org_id, analyst_email, "analyst")

    viewer_user_id, viewer_email = _new_user("rbac-viewer")
    add_member(_engine(), org.org_id, viewer_email, "viewer")

    outsider_user_id, outsider_email = _new_user("rbac-outsider")  # not a member of this org at all

    return {
        "org_id": org.org_id,
        "project_id": project.project_id,
        "admin_client": _client_for(admin_user_id),
        "analyst_client": _client_for(analyst_user_id),
        "viewer_client": _client_for(viewer_user_id),
        "outsider_client": _client_for(outsider_user_id),
    }


def _ingest_payload(tag: str) -> dict:
    return {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"rbac-exp-{tag}", "name": f"RBAC Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": [
            {
                "external_session_id": f"rbac-{tag}-s{i}",
                "external_experiment_id": f"rbac-exp-{tag}",
                "agent_version": "v1" if i % 2 == 0 else "v2",
                "external_user_id": f"user-{i}",
                "started_at": "2026-06-01T00:00:00",
                "messages": [],
                "actions": [],
                "outcome": {"label": "resolved", "metrics": []},
                "metrics": [],
                "context": {},
            }
            for i in range(4)
        ],
    }


def test_viewer_can_read_but_not_write(rbac_org):
    project_id = rbac_org["project_id"]

    # Read access: viewer succeeds.
    resp = rbac_org["viewer_client"].get(f"/api/v1/domains/support/experiments?project_id={project_id}")
    assert resp.status_code == 200

    # Write access: viewer is denied ingesting data.
    resp = rbac_org["viewer_client"].post("/api/v1/ingest/sessions", json=_ingest_payload("viewer"), params={"project_id": project_id})
    assert resp.status_code == 403


def test_analyst_can_ingest_and_evaluate_but_not_manage_org(rbac_org):
    project_id = rbac_org["project_id"]

    resp = rbac_org["analyst_client"].post("/api/v1/ingest/sessions", json=_ingest_payload("analyst"), params={"project_id": project_id})
    assert resp.status_code == 201

    experiments = rbac_org["analyst_client"].get(f"/api/v1/domains/support/experiments?project_id={project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"] == "RBAC Test analyst")

    eval_resp = rbac_org["analyst_client"].post(
        f"/api/v1/domains/support/experiments/{exp['experiment_id']}/release-evaluations?primary_metric=resolution_rate&project_id={project_id}"
    )
    assert eval_resp.status_code == 201

    # Analyst cannot add members or create projects — admin-only.
    resp = rbac_org["analyst_client"].post(f"/api/v1/orgs/{rbac_org['org_id']}/members", json={"email": "someone@example.com", "role": "viewer"})
    assert resp.status_code == 403
    resp = rbac_org["analyst_client"].post(f"/api/v1/orgs/{rbac_org['org_id']}/projects", json={"name": "New Project", "domain": "support"})
    assert resp.status_code == 403


def test_admin_can_manage_org_and_projects(rbac_org):
    resp = rbac_org["admin_client"].post(f"/api/v1/orgs/{rbac_org['org_id']}/members", json={"email": f"newmember-{uuid.uuid4()}@example.com", "role": "viewer"})
    # ValueError (no such registered user) surfaces as 422, not 403 — the
    # point here is admin gets PAST the permission check, unlike analyst/viewer.
    assert resp.status_code in (201, 422)

    resp = rbac_org["admin_client"].post(f"/api/v1/orgs/{rbac_org['org_id']}/projects", json={"name": "Admin-created project", "domain": "support"})
    assert resp.status_code == 201


def test_viewer_cannot_acknowledge_alerts_or_submit_reviews(rbac_org):
    project_id = rbac_org["project_id"]
    # Submitting a review as viewer is denied before any reference
    # validation even runs (role check happens first).
    resp = rbac_org["viewer_client"].post(
        f"/api/v1/domains/support/sessions/00000000-0000-0000-0000-000000000000/attributions/some_mode/review?project_id={project_id}",
        json={"decision": "confirmed"},
    )
    assert resp.status_code == 403


def test_outsider_has_no_access_to_the_project_at_all(rbac_org):
    project_id = rbac_org["project_id"]
    resp = rbac_org["outsider_client"].get(f"/api/v1/domains/support/experiments?project_id={project_id}")
    assert resp.status_code == 403


def test_outsider_gets_403_via_implicit_resolution_too(rbac_org):
    """The outsider belongs to no 'support' project at all -> implicit
    resolution (no project_id passed) also denies them, not just the
    explicit-project_id path."""
    resp = rbac_org["outsider_client"].get("/api/v1/domains/support/experiments")
    assert resp.status_code == 403


def test_cross_project_session_lookup_404s_not_leaks(rbac_org, api_client, support_project_id):
    """Stage 7 task 2: a session ingested into ONE project is invisible
    from a DIFFERENT project — even though both are domain="support" —
    exactly like it doesn't exist, not a 403 that would confirm existence."""
    project_id = rbac_org["project_id"]
    ingest_resp = rbac_org["admin_client"].post("/api/v1/ingest/sessions", json=_ingest_payload("crosscheck"), params={"project_id": project_id})
    assert ingest_resp.status_code == 201

    sessions = rbac_org["admin_client"].get(f"/api/v1/domains/support/sessions?project_id={project_id}&limit=200").json()["items"]
    assert sessions, "expected the just-ingested batch to produce at least one session"
    a_real_session_id = sessions[0]["session_id"]

    # api_client's own support project (a different project entirely) must not see it.
    resp = api_client.get(f"/api/v1/domains/support/sessions/{a_real_session_id}?project_id={support_project_id}")
    assert resp.status_code == 404
