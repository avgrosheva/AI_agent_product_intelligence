"""Shared test helpers for the connector test suites (Stages 9-10). Not a
test module itself (no `test_` prefix, so pytest never collects it) —
just the fixture-building and fake-transport code
tests/test_langfuse_connector_api.py and
tests/test_postgres_business_connector_api.py both need, so the Stage 10
end-to-end test can build the same realistic Langfuse-imported support
sessions Stage 9 proved, without duplicating that fixture code."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from backend.connectors.langfuse.client import LangfuseClient
from backend.connectors.langfuse.config import LangfuseConnectionConfig

DUMMY_LANGFUSE_CONFIG = LangfuseConnectionConfig(public_key="pub_test", secret_key="sk_test", host="https://fake.langfuse.test")


class FakeLangfuseResponse:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.text = str(body)

    def json(self) -> dict:
        return self._body


class DispatchingLangfuseTransport:
    """Routes GET calls by URL suffix: the list endpoint returns one
    page of trace-id summaries, and the per-trace detail endpoint
    returns that trace's full fixture dict."""

    def __init__(self, list_page: dict, detail_by_id: dict[str, dict]):
        self._list_page = list_page
        self._detail_by_id = detail_by_id
        self.get_calls = 0

    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> FakeLangfuseResponse:
        self.get_calls += 1
        if url.endswith("/api/public/traces"):
            return FakeLangfuseResponse(200, self._list_page)
        trace_id = url.rsplit("/", 1)[-1]
        return FakeLangfuseResponse(200, self._detail_by_id[trace_id])


class AlwaysFailingLangfuseTransport:
    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> FakeLangfuseResponse:
        return FakeLangfuseResponse(500, {})


def make_langfuse_trace(trace_id: str, version: str, outcome_label: str, minute_offset: int) -> dict:
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


def build_langfuse_rollback_fixture(tag: str, n_per_arm: int = 40) -> tuple[dict, dict[str, dict]]:
    """v1 resolves 90% of the time, v2 only 60% -- a large, reliable
    regression (matching tests/test_alerts_integration.py's own fixture
    ratios) so the release evaluation reliably reaches ROLLBACK and an
    alert fires, without depending on random variance."""
    details: dict[str, dict] = {}
    for i in range(n_per_arm):
        outcome = "resolved" if i % 10 < 9 else "escalated"
        trace_id = f"lf-{tag}-v1-{i}"
        details[trace_id] = make_langfuse_trace(trace_id, "v1", outcome, i)
    for i in range(n_per_arm):
        outcome = "resolved" if i % 10 < 6 else "escalated"
        trace_id = f"lf-{tag}-v2-{i}"
        details[trace_id] = make_langfuse_trace(trace_id, "v2", outcome, n_per_arm + i)
    list_page = {"data": [{"id": tid} for tid in details], "meta": {"page": 1, "totalPages": 1}}
    return list_page, details


def fake_langfuse_client(list_page: dict, details: dict[str, dict]) -> LangfuseClient:
    transport = DispatchingLangfuseTransport(list_page, details)
    return LangfuseClient(config=DUMMY_LANGFUSE_CONFIG, transport=transport, sleep_fn=lambda s: None)


def patch_langfuse_client(monkeypatch, client: LangfuseClient) -> None:
    from backend.app.routers import langfuse_connector

    monkeypatch.setattr(langfuse_connector, "_build_client", lambda host_override=None: client)


def langfuse_import_payload(mode: str, tag: str, **mapping_overrides) -> dict:
    # start/end are derived per-tag (not a fixed constant) because, absent
    # an explicit experiment mapping, the connector derives the experiment's
    # external id from this date range alone -- two tests sharing one
    # project and one fixed date range would otherwise collide on the SAME
    # experiment row, exactly the cross-test collision Stage 8 exists to
    # prevent. The fixture's own trace/observation timestamps are
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


def new_support_project(test_identity, name_prefix: str = "Isolation Project") -> str:
    from sqlalchemy import create_engine

    from backend.app.db import get_database_url
    from backend.auth.service import create_project

    engine = create_engine(get_database_url())
    return create_project(engine, test_identity["org_id"], f"{name_prefix} {uuid.uuid4().hex[:8]}", "support").project_id
