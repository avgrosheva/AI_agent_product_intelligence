"""Stage 8: tenancy hardening — ingestion identity isolation across
projects, valid-domain enforcement, commerce project isolation, legacy
(project_id IS NULL) data safety, and production JWT-secret validation."""

from __future__ import annotations

import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

from backend.app.db import get_database_url
from backend.auth.service import create_project


def _engine():
    return create_engine(get_database_url())


def _new_support_project(test_identity, name: str) -> str:
    return create_project(_engine(), test_identity["org_id"], name, "support").project_id


def _support_payload(external_experiment_id: str, external_session_id: str) -> dict:
    return {
        "domain": "support",
        "experiments": [{"external_experiment_id": external_experiment_id, "name": "Shared ID Test", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": [
            {
                "external_session_id": external_session_id,
                "external_experiment_id": external_experiment_id,
                "agent_version": "v1",
                "external_user_id": "user1",
                "started_at": "2026-09-01T00:00:00",
                "messages": [],
                "actions": [],
                "outcome": {"label": "resolved", "metrics": []},
                "metrics": [{"name": "handle_time_seconds", "value": 100.0}],
                "context": {},
            }
        ],
    }


def test_same_external_ids_in_two_projects_do_not_collide(api_client, test_identity):
    """Stage 8 task 1: two different projects ingesting the identical
    external_experiment_id/external_session_id under the same domain must
    end up as two SEPARATE rows, neither overwriting the other."""
    shared_ext_exp = f"shared-exp-{uuid.uuid4().hex[:8]}"
    shared_ext_sess = f"shared-sess-{uuid.uuid4().hex[:8]}"
    payload = _support_payload(shared_ext_exp, shared_ext_sess)

    project_a = _new_support_project(test_identity, "Collision Test A")
    project_b = _new_support_project(test_identity, "Collision Test B")

    resp_a = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_a})
    resp_b = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_b})
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201

    with _engine().connect() as conn:
        rows = conn.execute(
            text("SELECT project_id, experiment_id::text AS experiment_id FROM ingested_experiments WHERE external_experiment_id = :ext"),
            {"ext": shared_ext_exp},
        ).mappings().all()
    assert len(rows) == 2, "expected one experiment row PER project, not one shared/overwritten row"
    assert {r["project_id"] for r in rows} == {project_a, project_b}
    assert len({r["experiment_id"] for r in rows}) == 2  # distinct internal ids too

    with _engine().connect() as conn:
        session_rows = conn.execute(
            text("SELECT project_id, session_id::text AS session_id FROM ingested_sessions WHERE external_session_id = :ext"),
            {"ext": shared_ext_sess},
        ).mappings().all()
    assert len(session_rows) == 2
    assert {r["project_id"] for r in session_rows} == {project_a, project_b}
    assert len({r["session_id"] for r in session_rows}) == 2

    # Each project only ever sees ITS OWN copy through the adapter, never
    # the other's, and never both merged into one.
    exp_a = next(e for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={project_a}").json()["experiments"] if e["name"] == "Shared ID Test")
    exp_b = next(e for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={project_b}").json()["experiments"] if e["name"] == "Shared ID Test")
    assert exp_a["experiment_id"] != exp_b["experiment_id"]


def test_reingesting_same_project_same_external_id_still_upserts(api_client, test_identity):
    """The fix for cross-project collisions must not break same-project
    idempotency — re-ingesting into the SAME project still updates in
    place, not duplicates."""
    ext_exp = f"exp-{uuid.uuid4().hex[:8]}"
    ext_sess = f"sess-{uuid.uuid4().hex[:8]}"
    project_id = _new_support_project(test_identity, "Idempotency Recheck")
    payload = _support_payload(ext_exp, ext_sess)

    r1 = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    r2 = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["sessions_ingested"] == r2.json()["sessions_ingested"] == 1

    with _engine().connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM ingested_sessions WHERE external_session_id = :ext"), {"ext": ext_sess}).scalar_one()
    assert n == 1


def test_create_project_rejects_unknown_domain(api_client, test_identity):
    resp = api_client.post(f"/api/v1/orgs/{test_identity['org_id']}/projects", json={"name": "Bad Domain Project", "domain": "not_a_real_domain"})
    assert resp.status_code == 422


def test_create_project_accepts_registered_domains(api_client, test_identity):
    for domain in ("commerce", "support"):
        resp = api_client.post(f"/api/v1/orgs/{test_identity['org_id']}/projects", json={"name": f"Valid {domain}", "domain": domain})
        assert resp.status_code == 201


def test_commerce_cross_project_isolation(api_client, test_identity):
    """Stage 8 task 3: a second commerce-domain project that never claims
    the (single, shared) demo dataset sees ZERO experiments/sessions —
    never test_identity's data, and never an error."""
    unclaimed_project = _engine_create_commerce_project(test_identity)

    unclaimed_resp = api_client.get(f"/api/v1/domains/commerce/experiments?project_id={unclaimed_project}")
    assert unclaimed_resp.status_code == 200
    assert unclaimed_resp.json()["experiments"] == []

    unclaimed_sessions = api_client.get(f"/api/v1/domains/commerce/sessions?project_id={unclaimed_project}&limit=5")
    assert unclaimed_sessions.status_code == 200
    assert unclaimed_sessions.json()["items"] == []
    assert unclaimed_sessions.json()["total"] == 0

    # The already-claimed project is completely unaffected by the second
    # project's mere existence.
    claimed_resp = api_client.get(f"/api/v1/domains/commerce/experiments?project_id={test_identity['commerce_project_id']}")
    assert claimed_resp.status_code == 200
    assert len(claimed_resp.json()["experiments"]) >= 1


def test_commerce_cross_project_session_detail_404s(api_client, test_identity):
    """An unclaimed commerce project can't look up a session that belongs
    to a DIFFERENT (claimed) project's dataset either — 404, not the
    session's real data."""
    claimed_sessions = api_client.get(f"/api/v1/domains/commerce/sessions?project_id={test_identity['commerce_project_id']}&limit=1").json()["items"]
    assert claimed_sessions
    real_session_id = claimed_sessions[0]["session_id"]

    unclaimed_project = _engine_create_commerce_project(test_identity)
    resp = api_client.get(f"/api/v1/domains/commerce/sessions/{real_session_id}?project_id={unclaimed_project}")
    assert resp.status_code == 404


def test_claiming_commerce_dataset_is_explicit_not_automatic(test_identity):
    """Stage 8 task 3: creating a commerce project does NOT automatically
    grant it the dataset — claim_commerce_dataset must be called
    explicitly (as test_identity's fixture does for its own project)."""
    from backend.domains.commerce.ownership import get_commerce_dataset_owner

    fresh_project_id = _engine_create_commerce_project(test_identity)
    owner = get_commerce_dataset_owner(_engine())
    assert owner == test_identity["commerce_project_id"]
    assert owner != fresh_project_id


def _engine_create_commerce_project(test_identity) -> str:
    return create_project(_engine(), test_identity["org_id"], f"Unclaimed Commerce {uuid.uuid4().hex[:8]}", "commerce").project_id


def test_legacy_null_project_ingested_sessions_invisible_to_every_project(api_client, test_identity):
    """Stage 8 task 4: a row with project_id IS NULL (pre-Stage-7 data, or
    any row that predates project scoping) must not be exposed to ANY
    project — not test_identity's, not a fresh one's."""
    ext_sess = f"legacy-{uuid.uuid4().hex[:8]}"
    ext_exp = f"legacy-exp-{uuid.uuid4().hex[:8]}"
    with _engine().begin() as conn:
        exp_id = uuid.uuid4()
        sess_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO ingested_experiments (experiment_id, domain, project_id, external_experiment_id, name, control_version, treatment_version, created_at) "
                "VALUES (:eid, 'support', NULL, :ext_exp, 'Legacy Unowned', 'v1', 'v2', now())"
            ),
            {"eid": exp_id, "ext_exp": ext_exp},
        )
        conn.execute(
            text(
                "INSERT INTO ingested_sessions (session_id, domain, project_id, external_session_id, experiment_id, agent_version, started_at, outcome_label, created_at) "
                "VALUES (:sid, 'support', NULL, :ext_sess, :eid, 'v1', now(), 'resolved', now())"
            ),
            {"sid": sess_id, "ext_sess": ext_sess, "eid": exp_id},
        )

    # No project — not test_identity's own support project, not a fresh
    # one — can see this legacy row through the adapter.
    resp = api_client.get(f"/api/v1/domains/support/experiments?project_id={test_identity['support_project_id']}")
    names = {e["name"] for e in resp.json()["experiments"]}
    assert "Legacy Unowned" not in names

    fresh_project = _new_support_project(test_identity, "Fresh For Legacy Check")
    resp2 = api_client.get(f"/api/v1/domains/support/experiments?project_id={fresh_project}")
    names2 = {e["name"] for e in resp2.json()["experiments"]}
    assert "Legacy Unowned" not in names2


def test_backfill_migration_populated_session_project_id_from_experiment(test_identity, api_client):
    """Stage 8 task 1/4: the migration backfilling ingested_sessions.
    project_id from its owning experiment must hold for every row this
    session's own tests create too (a fresh ingest, not just historical
    data) — the two columns should never disagree."""
    ext_exp = f"consistency-exp-{uuid.uuid4().hex[:8]}"
    ext_sess = f"consistency-sess-{uuid.uuid4().hex[:8]}"
    project_id = _new_support_project(test_identity, "Consistency Check")
    resp = api_client.post(
        "/api/v1/ingest/sessions", json=_support_payload(ext_exp, ext_sess), params={"project_id": project_id}
    )
    assert resp.status_code == 201

    with _engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT s.project_id AS session_project_id, e.project_id AS experiment_project_id "
                "FROM ingested_sessions s JOIN ingested_experiments e ON e.experiment_id = s.experiment_id "
                "WHERE s.external_session_id = :ext"
            ),
            {"ext": ext_sess},
        ).mappings().first()
    assert row["session_project_id"] == row["experiment_project_id"] == project_id


def test_production_env_refuses_to_start_with_dev_jwt_secret():
    """Stage 8 task 5: AIPI_ENV=production with no (or the fixed default)
    AIPI_JWT_SECRET must fail fast at import time, in a fresh process
    (module-level state means this can't be tested by mutating os.environ
    in-process against an already-imported module)."""
    import os

    env = dict(os.environ)
    env["AIPI_ENV"] = "production"
    env.pop("AIPI_JWT_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", "import backend.auth.security"],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "AIPI_JWT_SECRET" in result.stderr


def test_production_env_starts_fine_with_a_real_secret():
    import os

    env = dict(os.environ)
    env["AIPI_ENV"] = "production"
    env["AIPI_JWT_SECRET"] = "a-real-randomly-generated-production-secret"
    result = subprocess.run(
        [sys.executable, "-c", "import backend.auth.security; print('ok')"],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_development_env_is_fine_with_the_default_dev_secret():
    import os

    env = dict(os.environ)
    env.pop("AIPI_ENV", None)
    env.pop("AIPI_JWT_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", "import backend.auth.security; print('ok')"],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ok" in result.stdout
