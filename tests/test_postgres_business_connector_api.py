"""Stage 10 tasks 5-9: the Postgres business-data connector proven end to
end through the real API against a REAL local Postgres "customer
database" fixture (a separate database on the same local Postgres
instance the whole test suite already uses) — mapping correctness,
joins, duplicates, nulls, type mismatches, missing join keys, idempotent
re-import, tenant isolation, dry-run, transient-connection failure, and
the full pipeline: Langfuse traces -> ingestion -> Postgres business
enrichment -> metrics/economics -> release evaluation -> investigation
-> alert.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.db import get_database_url
from tests._connector_test_helpers import (
    build_langfuse_rollback_fixture,
    fake_langfuse_client,
    langfuse_import_payload,
    new_support_project,
    patch_langfuse_client,
)

# -- a real local Postgres "customer database" fixture -------------------


@pytest.fixture(scope="module")
def business_source_url() -> str:
    base = make_url(get_database_url())
    url = base.set(database=f"{base.database}_business_source")
    maintenance = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        maintenance.dispose()
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def business_source_engine(business_source_url):
    engine = create_engine(business_source_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS business_data"))
        conn.execute(
            text(
                "CREATE TABLE business_data ("
                "external_session_id text, external_user_id text, order_completed boolean, "
                "revenue_usd text, cost_usd text, resolved boolean, csat_score text, recorded_at timestamp)"
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_business_data(business_source_engine):
    with business_source_engine.begin() as conn:
        conn.execute(text("DELETE FROM business_data"))
    yield


@pytest.fixture
def business_env(monkeypatch, business_source_url):
    url = make_url(business_source_url)
    monkeypatch.setenv("BUSINESS_DB_HOST", url.host)
    monkeypatch.setenv("BUSINESS_DB_PORT", str(url.port))
    monkeypatch.setenv("BUSINESS_DB_NAME", url.database)
    monkeypatch.setenv("BUSINESS_DB_USER", url.username)
    monkeypatch.setenv("BUSINESS_DB_PASSWORD", url.password or "")
    monkeypatch.delenv("BUSINESS_DB_SSLMODE", raising=False)


def _insert_rows(engine, rows: list[dict]) -> None:
    columns = ["external_session_id", "external_user_id", "order_completed", "revenue_usd", "cost_usd", "resolved", "csat_score", "recorded_at"]
    with engine.begin() as conn:
        for row in rows:
            values = {c: row.get(c) for c in columns}
            conn.execute(
                text(
                    "INSERT INTO business_data (external_session_id, external_user_id, order_completed, revenue_usd, cost_usd, resolved, csat_score, recorded_at) "
                    "VALUES (:external_session_id, :external_user_id, :order_completed, :revenue_usd, :cost_usd, :resolved, :csat_score, :recorded_at)"
                ),
                values,
            )


def _source_payload(metrics: list[tuple[str, str, str]], join_key_column: str = "external_session_id", join_key_target: str = "external_session_id", timestamp_column: str | None = None) -> dict:
    return {
        "table": "business_data",
        "join": {"join_key_column": join_key_column, "join_key_target": join_key_target, "timestamp_column": timestamp_column},
        "metrics": [{"source_column": c, "metric_name": n, "value_type": t} for c, n, t in metrics],
    }


def _enrichment_payload(mode: str, **source_kwargs) -> dict:
    return {"domain": "support", "mode": mode, "source": _source_payload(**source_kwargs)}


def _ingest_session(api_client, project_id: str, external_session_id: str, tag: str, external_user_id: str | None = None) -> None:
    payload = {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"biz-exp-{tag}", "name": f"Business Enrichment Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": [
            {
                "external_session_id": external_session_id,
                "external_experiment_id": f"biz-exp-{tag}",
                "agent_version": "v1",
                "external_user_id": external_user_id,
                "started_at": "2026-09-01T00:00:00",
                "outcome": {"label": "resolved", "metrics": []},
                "metrics": [],
            }
        ],
    }
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201


def _enrich(api_client, project_id: str, payload: dict):
    return api_client.post(f"/api/v1/connectors/postgres-business/enrich?project_id={project_id}", json=payload)


# -- mapping correctness / joins ------------------------------------------


def test_mapping_correctness_numeric_and_boolean_metrics_persisted(api_client, support_project_id, business_source_engine, business_env, classified_engine):
    tag = f"map-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "order_completed": True, "revenue_usd": "42.50"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("import", metrics=[("order_completed", "order_completed", "boolean"), ("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_rows"] == 1
    assert body["metrics_persisted"] == 2

    rows = classified_engine.connect().execute(
        text("SELECT m.name, m.value FROM ingested_metrics m JOIN ingested_sessions s ON s.session_id = m.session_id WHERE s.external_session_id = :sid"),
        {"sid": sid},
    ).all()
    values = {r[0]: r[1] for r in rows}
    assert values["order_completed"] == 1.0
    assert values["revenue_usd"] == pytest.approx(42.50)


def test_unmatched_source_row_is_reported_not_silently_attached(api_client, support_project_id, business_source_engine, business_env):
    tag = f"unmatched-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    unknown_id = f"no-such-session-{tag}"
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": "10"}, {"external_session_id": unknown_id, "revenue_usd": "20"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_rows"] == 1
    assert len(body["unmatched_source_rows"]) == 1
    assert body["unmatched_source_rows"][0]["join_key_value"] == unknown_id
    assert "no ingested session" in body["unmatched_source_rows"][0]["reason"]


def test_join_by_external_user_id(api_client, support_project_id, business_source_engine, business_env):
    tag = f"userjoin-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    uid = f"biz-user-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag, external_user_id=uid)
    _insert_rows(business_source_engine, [{"external_user_id": uid, "csat_score": "4.5"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("import", join_key_column="external_user_id", join_key_target="external_user_id", metrics=[("csat_score", "csat_score", "numeric")]))
    assert resp.status_code == 200
    assert resp.json()["matched_rows"] == 1
    assert resp.json()["metrics_persisted"] == 1


# -- duplicates / nulls / type mismatches / missing keys ------------------


def test_conflicting_duplicate_rows_are_reported_as_validation_errors(api_client, support_project_id, business_source_engine, business_env):
    tag = f"dup-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": "10"}, {"external_session_id": sid, "revenue_usd": "99"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_rows"] == 0  # neither conflicting row was used
    assert len(body["validation_errors"]) == 1
    assert sid in body["validation_errors"][0]["join_key_value"]


def test_duplicate_rows_resolved_by_most_recent_timestamp(api_client, support_project_id, business_source_engine, business_env):
    tag = f"dupts-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(
        business_source_engine,
        [
            {"external_session_id": sid, "revenue_usd": "10", "recorded_at": "2026-01-01T00:00:00"},
            {"external_session_id": sid, "revenue_usd": "99", "recorded_at": "2026-06-01T00:00:00"},
        ],
    )

    resp = _enrich(api_client, support_project_id, _enrichment_payload("import", metrics=[("revenue_usd", "revenue_usd", "numeric")], timestamp_column="recorded_at"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_rows"] == 1
    assert body["validation_errors"] == []


def test_null_source_value_is_skipped_not_fabricated(api_client, support_project_id, business_source_engine, business_env):
    tag = f"null-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": None, "csat_score": "4.0"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("import", metrics=[("revenue_usd", "revenue_usd", "numeric"), ("csat_score", "csat_score", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["null_values_skipped"] == 1
    assert body["metrics_persisted"] == 1  # only csat_score


def test_type_mismatch_is_reported_not_crashed_on(api_client, support_project_id, business_source_engine, business_env):
    tag = f"typemismatch-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": "not-a-number"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("import", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics_persisted"] == 0
    assert len(body["validation_errors"]) == 1
    assert "not-a-number" in body["validation_errors"][0]["message"]


def test_missing_join_key_value_is_unmatched_with_a_specific_reason(api_client, support_project_id, business_source_engine, business_env):
    _insert_rows(business_source_engine, [{"external_session_id": None, "revenue_usd": "10"}])
    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["unmatched_source_rows"]) == 1
    assert "no value in join_key_column" in body["unmatched_source_rows"][0]["reason"]


# -- dry-run / idempotency / tenancy / failure handling -------------------


def test_dry_run_makes_no_database_writes(api_client, support_project_id, business_source_engine, business_env, classified_engine):
    tag = f"dryrun-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": "10"}])

    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 200
    assert resp.json()["matched_rows"] == 1

    count = classified_engine.connect().execute(
        text("SELECT count(*) FROM ingested_metrics m JOIN ingested_sessions s ON s.session_id = m.session_id WHERE s.external_session_id = :sid AND m.name = 'revenue_usd'"),
        {"sid": sid},
    ).scalar_one()
    assert count == 0


def test_idempotent_reimport_does_not_duplicate_metric_rows(api_client, support_project_id, business_source_engine, business_env, classified_engine):
    tag = f"idem-{uuid.uuid4().hex[:8]}"
    sid = f"biz-sess-{tag}"
    _ingest_session(api_client, support_project_id, sid, tag)
    _insert_rows(business_source_engine, [{"external_session_id": sid, "revenue_usd": "10"}])
    payload = _enrichment_payload("import", metrics=[("revenue_usd", "revenue_usd", "numeric")])

    first = _enrich(api_client, support_project_id, payload)
    second = _enrich(api_client, support_project_id, payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["metrics_persisted"] == 1
    assert second.json()["metrics_persisted"] == 1

    count = classified_engine.connect().execute(
        text("SELECT count(*) FROM ingested_metrics m JOIN ingested_sessions s ON s.session_id = m.session_id WHERE s.external_session_id = :sid AND m.name = 'revenue_usd'"),
        {"sid": sid},
    ).scalar_one()
    assert count == 1


def test_tenant_isolation_same_external_session_id_two_projects(api_client, support_project_id, test_identity, business_source_engine, business_env, classified_engine):
    tag = f"tenant-{uuid.uuid4().hex[:8]}"
    shared_sid = f"shared-biz-sess-{tag}"
    other_project_id = new_support_project(test_identity, "Business Enrichment Isolation Project")

    _ingest_session(api_client, support_project_id, shared_sid, f"{tag}-a")
    _ingest_session(api_client, other_project_id, shared_sid, f"{tag}-b")
    _insert_rows(business_source_engine, [{"external_session_id": shared_sid, "revenue_usd": "77"}])

    payload = _enrichment_payload("import", metrics=[("revenue_usd", "revenue_usd", "numeric")])
    resp_a = _enrich(api_client, support_project_id, payload)
    assert resp_a.status_code == 200
    assert resp_a.json()["metrics_persisted"] == 1

    rows = classified_engine.connect().execute(
        text(
            "SELECT s.project_id, m.value FROM ingested_metrics m JOIN ingested_sessions s ON s.session_id = m.session_id "
            "WHERE s.external_session_id = :sid AND m.name = 'revenue_usd'"
        ),
        {"sid": shared_sid},
    ).all()
    assert len(rows) == 1  # only project A's session got the metric -- enriching project A never touched project B's
    assert str(rows[0][0]) == support_project_id


def test_business_source_connection_failure_surfaces_as_502(api_client, support_project_id, monkeypatch):
    monkeypatch.setenv("BUSINESS_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("BUSINESS_DB_PORT", "59999")
    monkeypatch.setenv("BUSINESS_DB_NAME", "nope")
    monkeypatch.setenv("BUSINESS_DB_USER", "nope")
    monkeypatch.setenv("BUSINESS_DB_PASSWORD", "nope")
    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 502


def test_missing_credentials_surface_as_503(api_client, support_project_id, monkeypatch):
    monkeypatch.delenv("BUSINESS_DB_HOST", raising=False)
    monkeypatch.delenv("BUSINESS_DB_NAME", raising=False)
    monkeypatch.delenv("BUSINESS_DB_USER", raising=False)
    monkeypatch.delenv("BUSINESS_DB_PASSWORD", raising=False)
    resp = _enrich(api_client, support_project_id, _enrichment_payload("dry_run", metrics=[("revenue_usd", "revenue_usd", "numeric")]))
    assert resp.status_code == 503


def test_unsafe_query_is_rejected_with_422(api_client, support_project_id, business_env):
    payload = {
        "domain": "support",
        "mode": "dry_run",
        "source": {
            "query": "SELECT * FROM business_data; DROP TABLE business_data",
            "join": {"join_key_column": "external_session_id"},
            "metrics": [{"source_column": "revenue_usd", "metric_name": "revenue_usd", "value_type": "numeric"}],
        },
    }
    resp = _enrich(api_client, support_project_id, payload)
    assert resp.status_code == 422


# -- full pipeline regression ----------------------------------------------


def test_full_pipeline_langfuse_and_postgres_enrichment_to_alert(api_client, support_project_id, business_source_engine, business_env, monkeypatch):
    tag = f"fullpipe-{uuid.uuid4().hex[:8]}"
    list_page, details = build_langfuse_rollback_fixture(tag, n_per_arm=40)
    patch_langfuse_client(monkeypatch, fake_langfuse_client(list_page, details))

    lf_payload = langfuse_import_payload(
        "import", tag, external_experiment_id=f"biz-pipeline-exp-{tag}", name=f"Business Pipeline Test {tag}", control_version="v1", treatment_version="v2"
    )
    lf_resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=lf_payload)
    assert lf_resp.status_code == 200
    assert lf_resp.json()["ingestion"]["sessions_ingested"] == 80

    # Every Langfuse trace id in this fixture IS its own external_session_id
    # (see backend.connectors.langfuse mapper/tests) -- the business source
    # enriches those same sessions with cost/revenue the agent trace itself
    # never carries, keyed by that exact id.
    business_rows = [
        {
            "external_session_id": trace_id,
            "cost_usd": "1.20" if d["release"] == "v1" else "0.90",
            "revenue_usd": "25.00" if d["metadata"]["ticket_outcome"] == "resolved" else "0.00",
        }
        for trace_id, d in details.items()
    ]
    _insert_rows(business_source_engine, business_rows)

    enrich_resp = _enrich(
        api_client,
        support_project_id,
        _enrichment_payload("import", metrics=[("cost_usd", "cost_usd", "numeric"), ("revenue_usd", "revenue_usd", "numeric")]),
    )
    assert enrich_resp.status_code == 200
    enrich_body = enrich_resp.json()
    assert enrich_body["matched_rows"] == 80
    assert enrich_body["metrics_persisted"] == 160  # 2 metrics x 80 sessions
    assert enrich_body["unmatched_source_rows"] == []

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp_id = next(e["experiment_id"] for e in experiments if e["name"] == f"Business Pipeline Test {tag}")

    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    eval_body = eval_resp.json()
    assert eval_body["status"] == "ROLLBACK"

    economics = eval_body["economics"]
    assert economics is not None
    assert economics["cost_per_session_v1"] is not None
    assert economics["cost_per_session_v2"] is not None
    assert economics["estimated_business_impact_per_session"] is not None  # real Postgres-sourced revenue, not null

    investigation = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/investigation?primary_metric=resolution_rate&project_id={support_project_id}")
    assert investigation.status_code == 200

    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    assert any(a["rule"] == "rollback" for a in alerts)
