"""Stage 7 task 1/8: registration, login, password hashing, and JWT
verification — using the app's real HTTP surface (api_client), not the
service layer directly, so this proves the actual wire contract."""

from __future__ import annotations

import uuid


def _unique_email() -> str:
    return f"auth-test-{uuid.uuid4()}@example.com"


def test_register_creates_a_user(api_client):
    email = _unique_email()
    resp = api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert "user_id" in body
    assert "password" not in body and "password_hash" not in body  # never echoed back


def test_register_rejects_duplicate_email(api_client):
    email = _unique_email()
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "pw1"})
    resp = api_client.post("/api/v1/auth/register", json={"email": email, "password": "pw2"})
    assert resp.status_code == 409


def test_password_is_hashed_not_stored_in_plaintext():
    from sqlalchemy import create_engine

    from backend.app.db import get_database_url
    from backend.auth.service import register_user

    engine = create_engine(get_database_url())
    email = _unique_email()
    register_user(engine, email, "hunter2")

    from sqlalchemy import select
    from sqlalchemy.orm import Session as OrmSession

    from backend.auth.models import PlatformUser as User

    with OrmSession(engine) as session:
        row = session.execute(select(User).where(User.email == email.lower())).scalar_one()
    assert row.password_hash != "hunter2"
    assert row.password_hash.startswith("$2b$") or row.password_hash.startswith("$2a$")  # bcrypt


def test_login_succeeds_with_correct_password_and_returns_a_bearer_token(api_client):
    email = _unique_email()
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-password"})
    resp = api_client.post("/api/v1/auth/login", json={"email": email, "password": "correct-password"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_fails_with_wrong_password(api_client):
    email = _unique_email()
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-password"})
    resp = api_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_fails_for_unknown_email(api_client):
    resp = api_client.post("/api/v1/auth/login", json={"email": _unique_email(), "password": "whatever"})
    assert resp.status_code == 401


def test_protected_endpoint_rejects_missing_token():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as anon_client:
        resp = anon_client.get("/api/v1/domains")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_garbage_token():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as anon_client:
        anon_client.headers["Authorization"] = "Bearer not-a-real-jwt"
        resp = anon_client.get("/api/v1/domains")
    assert resp.status_code == 401


def test_protected_endpoint_accepts_a_freshly_issued_token(api_client):
    email = _unique_email()
    api_client.post("/api/v1/auth/register", json={"email": email, "password": "correct-password"})
    token = api_client.post("/api/v1/auth/login", json={"email": email, "password": "correct-password"}).json()["access_token"]

    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as fresh_client:
        fresh_client.headers["Authorization"] = f"Bearer {token}"
        resp = fresh_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == email


def test_me_lists_memberships_and_projects(api_client, test_identity):
    resp = api_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == test_identity["email"]
    org_ids = {m["org_id"] for m in body["memberships"]}
    assert test_identity["org_id"] in org_ids
    project_ids = {p["project_id"] for p in body["projects"]}
    assert test_identity["commerce_project_id"] in project_ids
    assert test_identity["support_project_id"] in project_ids
