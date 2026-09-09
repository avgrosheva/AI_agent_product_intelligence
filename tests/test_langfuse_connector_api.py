"""Stage 9 tasks 5-7: the Langfuse connector proven end to end through
the real API — idempotent re-import, dry-run makes zero database writes,
tenant isolation between two projects, a failed Langfuse API call
surfaces as 502, an ambiguous experiment mapping is rejected with 422,
missing credentials surface as 503, and the full pipeline (Langfuse
traces -> ingestion -> metrics -> release evaluation -> investigation ->
alert) resolves exactly like a native-ingested support experiment does.

No real network access: backend.app.routers.langfuse_connector._build_client
is monkeypatched per test to return a LangfuseClient wired to a small
in-memory fake HTTP transport instead of a real Langfuse server."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from backend.app.routers import langfuse_connector
from backend.connectors.langfuse.client import LangfuseClient
from backend.connectors.langfuse.config import LangfuseConnectionConfig

DUMMY_CONFIG = LangfuseConnectionConfig(public_key="pub_test", secret_key="sk_test", host="https://fake.langfuse.test")


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.text = str(body)

    def json(self) -> dict:
        return self._body


class _DispatchingTransport:
    """Routes GET calls by URL suffix: the list endpoint returns one
    page of trace-id summaries, and the per-trace detail endpoint
    returns that trace's full fixture dict."""

    def __init__(self, list_page: dict, detail_by_id: dict[str, dict]):
        self._list_page = list_page
        self._detail_by_id = detail_by_id
        self.get_calls = 0

    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> _FakeResponse:
        self.get_calls += 1
        if url.endswith("/api/public/traces"):
            return _FakeResponse(200, self._list_page)
        trace_id = url.rsplit("/", 1)[-1]
        return _FakeResponse(200, self._detail_by_id[trace_id])


class _AlwaysFailingTransport:
    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(500, {})


def _make_trace(trace_id: str, version: str, outcome_label: str, minute_offset: int) -> dict:
    started = datetime(2026, 8, 1, 0, 0, 0) + timedelta(minutes=minute_offset)
    ended = started + timedelta(seconds=2)
    observation = {
        "id": f"{trace_id}-gen0",
        "type": "GENERATION",
        "name": "triage_ticket",
        "startTime": started.isoformat(),
        "endTime": ended.isoformat(),
        "model": version,
        "level": "DEFAULT",
        "input": [{"role": "user", "content": "I need help with my order"}],
        "output": {"role": "assistant", "content": "Let me help you with that."},
        "usage": {"input": 50, "output": 30, "total": 80},
        "calculatedTotalCost": 0.002,
    }
    return {
        "id": trace_id,
        "sessionId": trace_id,
        "userId": f"user-{trace_id}",
        "timestamp": started.isoformat(),
        "release": version,
        "tags": ["regression-fixture"],
        "metadata": {"ticket_outcome": outcome_label, "ticket_category": "billing"},
        "observations": [observation],
    }


def _build_rollback_fixture(tag: str, n_per_arm: int = 40) -> tuple[dict, dict[str, dict]]:
    """v1 resolves 90% of the time, v2 only 60% -- a large, reliable
    regression (matching tests/test_alerts_integration.py's own fixture
    ratios) so the release evaluation reliably reaches ROLLBACK and an
    alert fires, without depending on random variance."""
    details: dict[str, dict] = {}
    for i in range(n_per_arm):
        outcome = "resolved" if i % 10 < 9 else "escalated"
        trace_id = f"lf-{tag}-v1-{i}"
        details[trace_id] = _make_trace(trace_id, "v1", outcome, i)
    for i in range(n_per_arm):
        outcome = "resolved" if i % 10 < 6 else "escalated"
        trace_id = f"lf-{tag}-v2-{i}"
        details[trace_id] = _make_trace(trace_id, "v2", outcome, n_per_arm + i)
    list_page = {"data": [{"id": tid} for tid in details], "meta": {"page": 1, "totalPages": 1}}
    return list_page, details


def _fake_client(list_page: dict, details: dict[str, dict]) -> LangfuseClient:
    transport = _DispatchingTransport(list_page, details)
    return LangfuseClient(config=DUMMY_CONFIG, transport=transport, sleep_fn=lambda s: None)


def _patch_client(monkeypatch, client: LangfuseClient) -> None:
    monkeypatch.setattr(langfuse_connector, "_build_client", lambda host_override=None: client)


def _import_payload(mode: str, tag: str, **mapping_overrides) -> dict:
    # start/end are derived per-tag (not a fixed constant) because, absent
    # an explicit experiment mapping, the connector derives the experiment's
    # external id from this date range alone (see
    # backend.connectors.langfuse.service._resolve_experiment) -- two tests
    # sharing one project and one fixed date range would otherwise collide
    # on the SAME experiment row, exactly the cross-test collision Stage 8
    # exists to prevent. The fixture's own trace/observation timestamps are
    # independent of this and stay fixed; the fake transport never filters
    # by fromTimestamp/toTimestamp anyway.
    day = datetime(2020, 1, 1) + timedelta(days=abs(hash(tag)) % 3000)
    mapping = {"outcome_metadata_key": "ticket_outcome", "version_field": "release"}
    mapping.update(mapping_overrides)
    return {
        "domain": "support",
        "start": day.isoformat(),
        "end": (day + timedelta(hours=3)).isoformat(),
        "mode": mode,
        "mapping": mapping,
    }


def _new_support_project(test_identity) -> str:
    from sqlalchemy import create_engine

    from backend.app.db import get_database_url
    from backend.auth.service import create_project

    engine = create_engine(get_database_url())
    return create_project(engine, test_identity["org_id"], f"Langfuse Isolation Project {uuid.uuid4().hex[:8]}", "support").project_id


def test_full_pipeline_langfuse_traces_to_alert(api_client, support_project_id, monkeypatch):
    tag = f"e2e-{uuid.uuid4().hex[:8]}"
    list_page, details = _build_rollback_fixture(tag)
    _patch_client(monkeypatch, _fake_client(list_page, details))

    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=_import_payload("import", tag))
    assert resp.status_code == 200
    body = resp.json()
    assert body["traces_fetched"] == 80
    assert body["sessions_skipped"] == 0
    assert body["ingestion"]["sessions_ingested"] == 80

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp = next(e for e in experiments if e["name"].startswith("Langfuse import"))
    exp_id = exp["experiment_id"]

    metrics = api_client.get(f"/api/v1/domains/support/experiments/{exp_id}/metrics?project_id={support_project_id}").json()["metrics"]
    assert any(m["metric_name"] == "resolution_rate" for m in metrics)

    eval_resp = api_client.post(
        f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}"
    )
    assert eval_resp.status_code == 201
    assert eval_resp.json()["status"] == "ROLLBACK"

    investigation = api_client.get(
        f"/api/v1/domains/support/experiments/{exp_id}/investigation?primary_metric=resolution_rate&project_id={support_project_id}"
    )
    assert investigation.status_code == 200

    alerts = api_client.get(f"/api/v1/alerts?domain=support&experiment_id={exp_id}&project_id={support_project_id}").json()["alerts"]
    rollback_alerts = [a for a in alerts if a["rule"] == "rollback"]
    assert len(rollback_alerts) == 1
    assert rollback_alerts[0]["severity"] == "critical"


def test_idempotent_reimport_does_not_duplicate_sessions(api_client, support_project_id, monkeypatch):
    tag = f"idem-{uuid.uuid4().hex[:8]}"
    list_page, details = _build_rollback_fixture(tag, n_per_arm=10)
    _patch_client(monkeypatch, _fake_client(list_page, details))
    # An explicit mapping (not auto-derivation) so this experiment's name
    # is unique to this test and can't be confused with another test's
    # own "Langfuse import ..." experiment sharing the same long-lived
    # support_project_id fixture (test_identity is session-scoped).
    payload = _import_payload("import", tag, external_experiment_id=f"langfuse-exp-{tag}", name=f"Langfuse Idempotency Test {tag}", control_version="v1", treatment_version="v2")

    first = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=payload)
    assert first.status_code == 200
    assert first.json()["ingestion"]["sessions_ingested"] == 20

    second = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=payload)
    assert second.status_code == 200
    assert second.json()["ingestion"]["sessions_ingested"] == 20  # still 20, not 40

    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp_id = next(e["experiment_id"] for e in experiments if e["name"] == f"Langfuse Idempotency Test {tag}")
    sessions = api_client.get(f"/api/v1/domains/support/sessions?experiment_id={exp_id}&limit=100&project_id={support_project_id}").json()
    assert len(sessions["items"]) == 20


def test_dry_run_makes_no_database_writes(api_client, support_project_id, monkeypatch):
    tag = f"dry-{uuid.uuid4().hex[:8]}"
    list_page, details = _build_rollback_fixture(tag, n_per_arm=5)
    _patch_client(monkeypatch, _fake_client(list_page, details))

    before = {e["experiment_id"] for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]}

    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=_import_payload("dry_run", tag))
    assert resp.status_code == 200
    body = resp.json()
    assert body["traces_fetched"] == 10
    assert body["sessions_mapped"] == 10
    assert len(body["sample_sessions"]) == 5
    assert body["derived_experiment"]["name"].startswith("Langfuse import")

    after = {e["experiment_id"] for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]}
    assert after == before  # nothing persisted


def test_tenant_isolation_between_two_projects_importing_the_same_trace_ids(api_client, support_project_id, test_identity, monkeypatch):
    tag = f"tenant-{uuid.uuid4().hex[:8]}"
    list_page, details = _build_rollback_fixture(tag, n_per_arm=5)
    other_project_id = _new_support_project(test_identity)

    # Explicit mapping, same for both projects (proving the SAME external
    # experiment/session ids, imported by two different projects, never
    # collide -- Stage 8's project-scoped identity hashing, re-proven end
    # to end through this connector), and unique to this test so it can't
    # be confused with another test's own experiment in the same
    # long-lived support_project_id fixture.
    payload = _import_payload("import", tag, external_experiment_id=f"langfuse-exp-{tag}", name=f"Langfuse Tenant Isolation Test {tag}", control_version="v1", treatment_version="v2")

    _patch_client(monkeypatch, _fake_client(list_page, details))
    resp_a = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=payload)
    assert resp_a.status_code == 200

    _patch_client(monkeypatch, _fake_client(list_page, details))  # fresh transport/call count, same trace ids
    resp_b = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={other_project_id}", json=payload)
    assert resp_b.status_code == 200
    assert resp_b.json()["ingestion"]["sessions_ingested"] == 10  # not skipped as "already exists" -- distinct project

    exp_a = next(e for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"] if e["name"] == f"Langfuse Tenant Isolation Test {tag}")
    exp_b = next(e for e in api_client.get(f"/api/v1/domains/support/experiments?project_id={other_project_id}").json()["experiments"] if e["name"] == f"Langfuse Tenant Isolation Test {tag}")
    assert exp_a["experiment_id"] != exp_b["experiment_id"]  # same external ids, distinct internal ids (Stage 8)

    sessions_b = api_client.get(f"/api/v1/domains/support/sessions?experiment_id={exp_b['experiment_id']}&limit=100&project_id={other_project_id}").json()["items"]
    victim_session_id = sessions_b[0]["session_id"]

    cross_project_lookup = api_client.get(f"/api/v1/domains/support/sessions/{victim_session_id}?project_id={support_project_id}")
    assert cross_project_lookup.status_code == 404  # project A can never see project B's Langfuse-imported session


def test_failed_langfuse_api_call_surfaces_as_502(api_client, support_project_id, monkeypatch):
    monkeypatch.setattr(langfuse_connector, "_build_client", lambda host_override=None: LangfuseClient(config=DUMMY_CONFIG, transport=_AlwaysFailingTransport(), sleep_fn=lambda s: None))
    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=_import_payload("dry_run", "failing-api"))
    assert resp.status_code == 502


def test_ambiguous_experiment_mapping_is_rejected_with_422(api_client, support_project_id, monkeypatch):
    tag = f"ambig-{uuid.uuid4().hex[:8]}"
    _, v1_details = _build_rollback_fixture(f"{tag}-a", n_per_arm=2)
    details = dict(v1_details)
    third_id = f"lf-{tag}-v3-0"
    details[third_id] = _make_trace(third_id, "v3", "resolved", 999)
    list_page = {"data": [{"id": tid} for tid in details], "meta": {"page": 1, "totalPages": 1}}
    _patch_client(monkeypatch, _fake_client(list_page, details))

    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=_import_payload("dry_run", tag))
    assert resp.status_code == 422
    assert "distinct agent version" in resp.json()["detail"]


def test_missing_credentials_surface_as_503(api_client, support_project_id, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=_import_payload("dry_run", "no-creds"))
    assert resp.status_code == 503
    assert "LANGFUSE_SECRET_KEY" in resp.json()["detail"]


def test_unknown_domain_is_rejected_before_any_langfuse_call(api_client, support_project_id, monkeypatch):
    payload = _import_payload("dry_run", "unknown-domain")
    payload["domain"] = "not-a-real-domain"
    resp = api_client.post(f"/api/v1/connectors/langfuse/import?project_id={support_project_id}", json=payload)
    assert resp.status_code == 422
