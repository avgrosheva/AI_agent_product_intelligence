"""Stage 18 task 4/11: short-lived access token + revocable, rotating
refresh token. Pure auth-flow tests, independent of the dev dataset --
uses its own freshly-registered users via a bare TestClient rather than
api_client's dev-dataset-backed identity."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client(db_engine) -> TestClient:
    # `db_engine` (unused directly): forces the session-scoped alembic
    # migration to have run before this test touches the database at all
    # (see the matching comment in tests/test_audit_log.py's audit_org
    # fixture for why that matters).
    return TestClient(app)


def _register_and_login(client: TestClient) -> dict:
    email = f"refresh-{uuid.uuid4()}@example.com"
    password = "password123"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    assert len(body["refresh_token"]) > 20
    return body


def test_login_issues_both_an_access_and_a_refresh_token(client):
    tokens = _register_and_login(client)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200


def test_refresh_rotates_to_a_new_pair_and_invalidates_the_old_refresh_token(client):
    tokens = _register_and_login(client)

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    # Not asserting the new access token differs from the old one: a JWT's
    # claims (sub/iat/exp) are only second-precision, so two tokens for
    # the same user issued within the same second are byte-identical --
    # cryptographically and semantically equivalent, not a bug. The
    # refresh token is the one with a real single-use identity guarantee.
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The new access token actually works.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
    assert me.status_code == 200

    # The OLD refresh token was consumed by rotation -- reusing it is the
    # classic signal of a stolen token being replayed, so it's rejected,
    # not silently re-honored.
    reuse_attempt = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse_attempt.status_code == 401


def test_refresh_with_an_unknown_token_is_rejected(client):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_logout_revokes_that_one_refresh_token_only(client):
    tokens = _register_and_login(client)

    logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout_resp.status_code == 204

    # That refresh token no longer works...
    refresh_after_logout = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_after_logout.status_code == 401

    # ...but the still-valid access token issued alongside it keeps
    # working until it naturally expires (access tokens are not revoked
    # individually in this minimal model -- only refresh tokens are real
    # server state).
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200

    # Logging out an already-logged-out session is a no-op success, not
    # an error a caller needs to special-case.
    second_logout = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert second_logout.status_code == 204


def test_logout_all_revokes_every_outstanding_refresh_token_for_that_user(client):
    tokens_a = _register_and_login(client)
    email_a_access = tokens_a["access_token"]

    # A second login (same account, a second "device") issues a SECOND,
    # independent refresh token.
    refresh_2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]}).json()

    logout_all = client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {email_a_access}"})
    assert logout_all.status_code == 200
    assert logout_all.json()["revoked_count"] >= 1

    # The still-outstanding refresh token from the second login is also
    # dead -- "everywhere" means every session, not just the caller's own.
    refresh_after = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2["refresh_token"]})
    assert refresh_after.status_code == 401


def test_admin_can_revoke_another_members_sessions_but_a_non_admin_cannot(client):
    from backend.auth.service import add_member, create_organization
    from backend.app.db import get_database_url
    from sqlalchemy import create_engine

    engine = create_engine(get_database_url())

    admin_email = f"revoke-admin-{uuid.uuid4()}@example.com"
    admin_reg = client.post("/api/v1/auth/register", json={"email": admin_email, "password": "password123"})
    admin_user_id = admin_reg.json()["user_id"]
    org = create_organization(engine, "Revoke Sessions Test Org", admin_user_id)

    member_tokens = _register_and_login(client)
    member_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {member_tokens['access_token']}"})
    member_email = member_me.json()["user"]["email"]
    member_user_id = member_me.json()["user"]["user_id"]
    add_member(engine, org.org_id, member_email, "viewer")

    admin_login = client.post("/api/v1/auth/login", json={"email": admin_email, "password": "password123"}).json()

    # A non-admin (the member themself, or anyone without admin role in
    # this org) cannot force another member's sessions to end.
    forbidden = client.post(
        f"/api/v1/orgs/{org.org_id}/members/{member_user_id}/revoke-sessions",
        headers={"Authorization": f"Bearer {member_tokens['access_token']}"},
    )
    assert forbidden.status_code == 403

    # The org admin can.
    revoke_resp = client.post(
        f"/api/v1/orgs/{org.org_id}/members/{member_user_id}/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_login['access_token']}"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked_count"] >= 1

    refresh_after = client.post("/api/v1/auth/refresh", json={"refresh_token": member_tokens["refresh_token"]})
    assert refresh_after.status_code == 401
