"""Stage 6 tasks 1-2/7: create alerts (deterministically, deduplicated
against existing OPEN alerts) from a release evaluation, and read/
acknowledge them. Never imports backend.domains.commerce or
backend.domains.support — domain/experiment_id here are just the strings
backend.release.service already carries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.alerts.models import Alert
from backend.alerts.rules import evaluate_alert_rules


@dataclass(frozen=True)
class AlertResult:
    alert_id: str
    domain: str
    experiment_id: str
    evaluation_id: str
    rule: str
    severity: str
    reason: str
    related_guardrail: str | None
    related_finding: str | None
    status: str
    created_at: datetime
    acknowledged_at: datetime | None = None
    project_id: str | None = None


def _row_to_result(row: Alert) -> AlertResult:
    return AlertResult(
        alert_id=str(row.alert_id), domain=row.domain, project_id=row.project_id, experiment_id=row.experiment_id, evaluation_id=row.evaluation_id,
        rule=row.rule, severity=row.severity, reason=row.reason, related_guardrail=row.related_guardrail,
        related_finding=row.related_finding, status=row.status, created_at=row.created_at, acknowledged_at=row.acknowledged_at,
    )


def generate_alerts_for_evaluation(
    engine: Engine, domain: str, experiment_id: str, evaluation_id: str, status: str, fields: dict, primary_metric: str, project_id: str | None = None
) -> list[AlertResult]:
    """Called right after a release evaluation is persisted
    (backend.release.service.evaluate_and_persist_release). Deterministic:
    the same (status, fields) always produces the same candidate alerts;
    only which of those are actually INSERTed depends on what's already
    open (dedup, scoped to the same project — Stage 7 task 2)."""
    candidates = evaluate_alert_rules(status, fields, primary_metric)
    if not candidates:
        return []

    created: list[AlertResult] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with OrmSession(engine) as session:
        for candidate in candidates:
            existing_open = session.execute(
                select(Alert).where(
                    Alert.domain == domain,
                    Alert.project_id == project_id,
                    Alert.experiment_id == experiment_id,
                    Alert.rule == candidate.rule,
                    Alert.related_guardrail == candidate.related_guardrail,
                    Alert.related_finding == candidate.related_finding,
                    Alert.status == "open",
                )
            ).scalar_one_or_none()
            if existing_open is not None:
                continue  # dedup: an open alert already covers this exact condition

            row = Alert(
                alert_id=uuid.uuid4(), domain=domain, project_id=project_id, experiment_id=experiment_id, evaluation_id=evaluation_id,
                rule=candidate.rule, severity=candidate.severity, reason=candidate.reason,
                related_guardrail=candidate.related_guardrail, related_finding=candidate.related_finding,
                status="open", created_at=now, acknowledged_at=None,
            )
            session.add(row)
            session.flush()
            created.append(_row_to_result(row))
        session.commit()
    return created


def list_alerts(
    engine: Engine,
    domain: str | None = None,
    project_id: str | None = None,
    experiment_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[AlertResult]:
    with OrmSession(engine) as session:
        stmt = select(Alert)
        if domain is not None:
            stmt = stmt.where(Alert.domain == domain)
        if project_id is not None:
            stmt = stmt.where(Alert.project_id == project_id)
        if experiment_id is not None:
            stmt = stmt.where(Alert.experiment_id == experiment_id)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [_row_to_result(r) for r in rows]


def get_alert(engine: Engine, alert_id: str, project_id: str | None = None) -> AlertResult | None:
    """`project_id`, when given, enforces tenant isolation at the service
    layer (Stage 7 task 2) — a caller cannot fetch an alert belonging to a
    different project by id even if they know it."""
    with OrmSession(engine) as session:
        row = session.get(Alert, uuid.UUID(alert_id))
    if row is None:
        return None
    if project_id is not None and row.project_id != project_id:
        return None
    return _row_to_result(row)


def acknowledge_alert(engine: Engine, alert_id: str, project_id: str | None = None) -> AlertResult | None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with OrmSession(engine) as session:
        row = session.get(Alert, uuid.UUID(alert_id))
        if row is None:
            return None
        if project_id is not None and row.project_id != project_id:
            return None
        if row.status == "open":
            row.status = "acknowledged"
            row.acknowledged_at = now
            session.commit()
            session.refresh(row)
        return _row_to_result(row)
