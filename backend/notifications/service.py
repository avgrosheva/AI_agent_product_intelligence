"""Stage 12 tasks 1-3: channel management and event dispatch. Dispatch
is deliberately simple, not a rules DSL (task 4's own constraint): a
project has a flat set of enabled event types
(backend.project_config.models.ProjectConfig.enabled_notification_rules)
and a flat set of enabled channels — when an enabled event fires, every
enabled channel gets notified, full stop.

Every dispatched event is generated purely from data already computed
and persisted by its caller (backend.release.service,
backend.monitoring.service) — this module never re-derives a verdict,
guardrail breach, or data-quality status itself.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from backend.notifications.client import DeliveryOutcome, deliver_slack, deliver_webhook, redact
from backend.notifications.models import NotificationChannel, NotificationDelivery

MAX_ATTEMPTS = 3
URL_PREVIEW_SUFFIX_LEN = 6


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class NotificationChannelResult:
    channel_id: str
    project_id: str
    channel_type: str
    url_preview: str
    enabled: bool
    created_at: datetime


@dataclass(frozen=True)
class NotificationDeliveryResult:
    notification_id: str
    project_id: str
    channel_id: str
    event_type: str
    dedup_key: str
    payload_summary: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None


def _url_preview(url: str) -> str:
    # Never the real URL -- a webhook URL is itself a bearer credential
    # (Stage 12 task 3: "do not log secrets or full webhook URLs"), so
    # even the API's own read path only ever returns a short suffix.
    if len(url) <= URL_PREVIEW_SUFFIX_LEN:
        return "…"
    return f"…{url[-URL_PREVIEW_SUFFIX_LEN:]}"


def _channel_to_result(row: NotificationChannel) -> NotificationChannelResult:
    return NotificationChannelResult(
        channel_id=str(row.channel_id), project_id=row.project_id, channel_type=row.channel_type,
        url_preview=_url_preview(row.url), enabled=row.enabled, created_at=row.created_at,
    )


def _delivery_to_result(row: NotificationDelivery) -> NotificationDeliveryResult:
    return NotificationDeliveryResult(
        notification_id=str(row.notification_id), project_id=row.project_id, channel_id=str(row.channel_id),
        event_type=row.event_type, dedup_key=row.dedup_key, payload_summary=row.payload_summary, status=row.status,
        attempts=row.attempts, last_error=row.last_error, created_at=row.created_at, delivered_at=row.delivered_at,
    )


def create_channel(engine: Engine, project_id: str, channel_type: str, url: str, enabled: bool = True) -> NotificationChannelResult:
    row = NotificationChannel(channel_id=uuid.uuid4(), project_id=project_id, channel_type=channel_type, url=url, enabled=enabled, created_at=_now())
    with OrmSession(engine) as session:
        session.add(row)
        session.commit()
        return _channel_to_result(row)


def list_channels(engine: Engine, project_id: str, enabled_only: bool = False) -> list[NotificationChannelResult]:
    with OrmSession(engine) as session:
        query = session.query(NotificationChannel).filter(NotificationChannel.project_id == project_id)
        if enabled_only:
            query = query.filter(NotificationChannel.enabled.is_(True))
        rows = query.order_by(NotificationChannel.created_at.desc()).all()
        return [_channel_to_result(r) for r in rows]


def list_deliveries(engine: Engine, project_id: str, limit: int = 50) -> list[NotificationDeliveryResult]:
    with OrmSession(engine) as session:
        rows = (
            session.query(NotificationDelivery)
            .filter(NotificationDelivery.project_id == project_id)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_delivery_to_result(r) for r in rows]


def _summarize(event_type: str, dedup_key: str, summary: dict) -> str:
    fields = ", ".join(f"{k}={v}" for k, v in summary.items())
    return f"{event_type} ({dedup_key}): {fields}" if fields else f"{event_type} ({dedup_key})"


def _deliver_with_retry(channel: NotificationChannel, payload_text: str, payload: dict, post_fn, sleep_fn) -> tuple[str, int, str | None]:
    attempts = 0
    outcome: DeliveryOutcome | None = None
    for attempt in range(MAX_ATTEMPTS):
        attempts += 1
        if channel.channel_type == "slack_webhook":
            outcome = deliver_slack(channel.url, payload_text, post_fn=post_fn)
        else:
            outcome = deliver_webhook(channel.url, payload, post_fn=post_fn)
        if outcome.success:
            return "delivered", attempts, None
        if attempt < MAX_ATTEMPTS - 1:
            sleep_fn(0.5 * (attempt + 1))
    return "failed", attempts, redact(outcome.error, channel.url) if outcome else "no attempt made"


def dispatch_event(
    engine: Engine,
    project_id: str | None,
    event_type: str,
    dedup_key: str,
    summary: dict,
    *,
    post_fn=None,
    sleep_fn=None,
) -> list[NotificationDeliveryResult]:
    """Notifies every enabled channel for this project if — and only if —
    `event_type` is one of this project's own enabled_notification_rules
    (backend.project_config). A project with no persisted config, or one
    that hasn't enabled this event type, gets no notification at all —
    opt-in, never a surprise default."""
    if project_id is None:
        return []

    from backend.project_config.service import get_project_config

    config = get_project_config(engine, project_id)
    enabled_rules = set(config.enabled_notification_rules) if config is not None else set()
    if event_type not in enabled_rules:
        return []

    channels = list_channels(engine, project_id, enabled_only=True)
    if not channels:
        return []

    sleep_fn = sleep_fn or time.sleep
    payload_text = _summarize(event_type, dedup_key, summary)
    payload = {"event_type": event_type, "project_id": project_id, "dedup_key": dedup_key, **summary}

    results: list[NotificationDeliveryResult] = []
    for channel_result in channels:
        with OrmSession(engine) as session:
            channel_id = uuid.UUID(channel_result.channel_id)
            existing = (
                session.query(NotificationDelivery)
                .filter(
                    NotificationDelivery.project_id == project_id,
                    NotificationDelivery.channel_id == channel_id,
                    NotificationDelivery.event_type == event_type,
                    NotificationDelivery.dedup_key == dedup_key,
                )
                .first()
            )
            if existing is not None:
                results.append(_delivery_to_result(existing))
                continue

            channel = session.get(NotificationChannel, channel_id)
            status, attempts, last_error = _deliver_with_retry(channel, payload_text, payload, post_fn, sleep_fn)
            now = _now()
            row = NotificationDelivery(
                notification_id=uuid.uuid4(), project_id=project_id, channel_id=channel_id, event_type=event_type,
                dedup_key=dedup_key, payload_summary=payload_text, status=status, attempts=attempts,
                last_error=last_error, created_at=now, delivered_at=now if status == "delivered" else None,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                # Lost a race with a concurrent dispatch for the exact
                # same event -- the unique constraint is the real
                # guarantee; fetch whichever row won and report that.
                session.rollback()
                winner = (
                    session.query(NotificationDelivery)
                    .filter(
                        NotificationDelivery.project_id == project_id,
                        NotificationDelivery.channel_id == channel_id,
                        NotificationDelivery.event_type == event_type,
                        NotificationDelivery.dedup_key == dedup_key,
                    )
                    .one()
                )
                results.append(_delivery_to_result(winner))
                continue
            results.append(_delivery_to_result(row))

    return results


def dispatch_release_notifications(engine: Engine, project_id: str | None, evaluation) -> list[NotificationDeliveryResult]:
    """Stage 12 task 2: ROLLBACK, HOLD, blocking guardrail breach, and
    critical data quality, read directly off an already-persisted
    ReleaseEvaluationResult (backend.release.service) — no statistics,
    no thresholds, no verdict logic lives here. Called once per
    evaluation, right after backend.alerts.service's own alert
    generation, from the same evaluate_and_persist_release."""
    results: list[NotificationDeliveryResult] = []
    dedup_key = evaluation.evaluation_id
    common = {"experiment_id": evaluation.experiment_id, "primary_metric": evaluation.primary_metric, "status": evaluation.status}

    if evaluation.status == "ROLLBACK":
        results += dispatch_event(engine, project_id, "ROLLBACK", dedup_key, common)
    elif evaluation.status == "HOLD":
        results += dispatch_event(engine, project_id, "HOLD", dedup_key, common)

    blocking = [g["name"] for g in evaluation.breached_guardrails if g.get("severity") == "blocking"]
    if blocking:
        results += dispatch_event(engine, project_id, "BLOCKING_GUARDRAIL_BREACH", dedup_key, {**common, "guardrails": blocking})

    if evaluation.data_quality_status == "critical":
        results += dispatch_event(engine, project_id, "CRITICAL_DATA_QUALITY", dedup_key, {**common, "data_quality_status": evaluation.data_quality_status})

    return results


def dispatch_monitoring_failure_notification(engine: Engine, project_id: str | None, run_id: str, config, failure_reason: str) -> list[NotificationDeliveryResult]:
    """Stage 12 task 2: a monitoring job's own already-recorded failure
    (backend.monitoring.service.run_monitoring_job) — the reason string
    is whatever exception message was already persisted onto the
    MonitoringRun row, never recomputed here."""
    return dispatch_event(
        engine, project_id, "MONITORING_JOB_FAILURE", run_id,
        {"config_id": config.config_id, "experiment_id": config.experiment_id, "primary_metric": config.primary_metric, "failure_reason": failure_reason},
    )
