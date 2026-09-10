"""Stage 12 tasks 1-3/8: channel/dispatch service — enabled-rules
gating, retry-then-persist, deduplication, secret redaction in the
delivery log, and tenant isolation. Uses a real Postgres-backed engine
(project_config + notification tables) with an injected fake HTTP
post_fn — no real network access, no real database mocking."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.notifications.service import create_channel, dispatch_event, list_channels, list_deliveries
from backend.project_config.service import upsert_project_config
from tests._connector_test_helpers import new_support_project

SECRET_URL = "https://hooks.example.com/T00/B00/supersecrettoken"


def _enable_rules(engine, project_id: str, rules: list[str]) -> None:
    upsert_project_config(
        engine, project_id, primary_metric=None, metrics_json=None, guardrails_json=None, segment_dimensions_json=None,
        economics_json=None, monitoring_cadence_seconds=None, enabled_notification_rules=rules,
    )


def test_no_notification_when_event_type_not_enabled(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Disabled Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["HOLD"])  # ROLLBACK not enabled

    results = dispatch_event(engine, project_id, "ROLLBACK", "eval-1", {"status": "ROLLBACK"}, post_fn=lambda u, p, t: 200)
    assert results == []
    assert list_deliveries(engine, project_id) == []


def test_no_notification_when_project_has_no_config_at_all(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif No Config Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    results = dispatch_event(engine, project_id, "ROLLBACK", "eval-1", {"status": "ROLLBACK"}, post_fn=lambda u, p, t: 200)
    assert results == []


def test_successful_webhook_delivery_is_logged(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Success Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["ROLLBACK"])

    results = dispatch_event(engine, project_id, "ROLLBACK", f"eval-{uuid.uuid4().hex[:8]}", {"status": "ROLLBACK"}, post_fn=lambda u, p, t: 200)
    assert len(results) == 1
    assert results[0].status == "delivered"
    assert results[0].attempts == 1
    assert results[0].delivered_at is not None


def test_retry_then_success_records_multiple_attempts(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Retry Success Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["ROLLBACK"])

    calls = {"n": 0}

    def flaky_post(url, payload, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            return 503
        return 200

    results = dispatch_event(
        engine, project_id, "ROLLBACK", f"eval-{uuid.uuid4().hex[:8]}", {"status": "ROLLBACK"}, post_fn=flaky_post, sleep_fn=lambda s: None
    )
    assert results[0].status == "delivered"
    assert results[0].attempts == 2


def test_exhausted_retries_is_persisted_as_failed_with_redacted_error(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Failure Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["MONITORING_JOB_FAILURE"])

    results = dispatch_event(
        engine, project_id, "MONITORING_JOB_FAILURE", f"run-{uuid.uuid4().hex[:8]}", {"reason": "boom"}, post_fn=lambda u, p, t: 500, sleep_fn=lambda s: None
    )
    assert results[0].status == "failed"
    assert results[0].attempts == 3
    assert results[0].last_error == "HTTP 500"
    assert SECRET_URL not in (results[0].last_error or "")


def test_secret_url_never_appears_in_delivery_log_or_channel_listing(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Redaction Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["ROLLBACK"])

    def raising_post(url, payload, timeout):
        raise ConnectionError(f"refused by {url}")

    dispatch_event(engine, project_id, "ROLLBACK", f"eval-{uuid.uuid4().hex[:8]}", {}, post_fn=raising_post, sleep_fn=lambda s: None)

    for delivery in list_deliveries(engine, project_id):
        assert SECRET_URL not in delivery.payload_summary
        assert SECRET_URL not in (delivery.last_error or "")

    for channel in list_channels(engine, project_id):
        assert SECRET_URL not in channel.url_preview
        assert channel.url_preview.endswith(SECRET_URL[-6:])


def test_notification_deduplication_same_event_delivered_once(test_identity):
    engine = create_engine(get_database_url())
    project_id = new_support_project(test_identity, "Notif Dedup Project")
    create_channel(engine, project_id, "webhook", SECRET_URL)
    _enable_rules(engine, project_id, ["ROLLBACK"])

    calls = {"n": 0}

    def counting_post(url, payload, timeout):
        calls["n"] += 1
        return 200

    dedup_key = f"eval-{uuid.uuid4().hex[:8]}"
    first = dispatch_event(engine, project_id, "ROLLBACK", dedup_key, {"status": "ROLLBACK"}, post_fn=counting_post)
    second = dispatch_event(engine, project_id, "ROLLBACK", dedup_key, {"status": "ROLLBACK"}, post_fn=counting_post)

    assert calls["n"] == 1  # the second call never even attempts delivery
    assert first[0].notification_id == second[0].notification_id
    assert len(list_deliveries(engine, project_id)) == 1

    # A genuinely different event (different dedup_key) DOES notify again.
    dispatch_event(engine, project_id, "ROLLBACK", f"eval-{uuid.uuid4().hex[:8]}", {"status": "ROLLBACK"}, post_fn=counting_post)
    assert calls["n"] == 2
    assert len(list_deliveries(engine, project_id)) == 2


def test_notifications_are_project_scoped(test_identity):
    engine = create_engine(get_database_url())
    project_a = new_support_project(test_identity, "Notif Isolation A")
    project_b = new_support_project(test_identity, "Notif Isolation B")
    create_channel(engine, project_a, "webhook", SECRET_URL)
    create_channel(engine, project_b, "webhook", SECRET_URL)
    _enable_rules(engine, project_a, ["ROLLBACK"])
    _enable_rules(engine, project_b, ["ROLLBACK"])

    dispatch_event(engine, project_a, "ROLLBACK", "shared-dedup-key", {}, post_fn=lambda u, p, t: 200)
    dispatch_event(engine, project_b, "ROLLBACK", "shared-dedup-key", {}, post_fn=lambda u, p, t: 200)

    deliveries_a = list_deliveries(engine, project_a)
    deliveries_b = list_deliveries(engine, project_b)
    assert len(deliveries_a) == 1
    assert len(deliveries_b) == 1
    assert deliveries_a[0].notification_id != deliveries_b[0].notification_id  # same dedup_key, different projects -- never merged

    assert all(c.project_id == project_a for c in list_channels(engine, project_a))
