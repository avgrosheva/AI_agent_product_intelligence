"""Stage 18 task 3: record and read privileged-action audit events. Pure
data-layer service, matching every other backend.*.service module's
convention -- no FastAPI imports here (those live in
backend.app.routers.audit), no domain package imports.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.audit.models import AuditLogEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditLogEntryResult:
    entry_id: str
    actor_user_id: str | None
    actor_email: str | None
    org_id: str | None
    project_id: str | None
    action: str
    target: str | None
    created_at: datetime
    event_metadata: dict


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row_to_result(row: AuditLogEntry) -> AuditLogEntryResult:
    return AuditLogEntryResult(
        entry_id=str(row.entry_id), actor_user_id=row.actor_user_id, actor_email=row.actor_email,
        org_id=row.org_id, project_id=row.project_id, action=row.action, target=row.target,
        created_at=row.created_at, event_metadata=row.event_metadata,
    )


def record_audit_event(
    engine: Engine,
    *,
    action: str,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    org_id: str | None = None,
    project_id: str | None = None,
    target: str | None = None,
    metadata: dict | None = None,
) -> AuditLogEntryResult:
    """Called AFTER the underlying privileged action has already
    committed -- this never gates or rolls back the action it describes.
    Best-effort by design: a failure writing the audit row is logged and
    swallowed, never raised, so an audit-log outage can't become an
    outage of the product feature it's describing.

    `metadata` must never carry secrets or raw sensitive payloads -- no
    passwords, tokens, webhook URLs, or full request/response bodies.
    Callers pass only small, already-safe-to-display structured fields
    (a changed-field list, a rule name, a decision value) -- the same
    redaction discipline backend.notifications.service already applies to
    channel URLs before they reach a delivery log."""
    entry_id = uuid.uuid4()
    created_at = _now()
    event_metadata = metadata or {}
    try:
        with OrmSession(engine) as session:
            session.add(AuditLogEntry(
                entry_id=entry_id, actor_user_id=actor_user_id, actor_email=actor_email, org_id=org_id,
                project_id=project_id, action=action, target=target, created_at=created_at, event_metadata=event_metadata,
            ))
            session.commit()
    except Exception:
        logger.exception("failed to record audit event action=%s target=%s", action, target)
    # Built from the same local values passed to the ORM row above, never
    # by reading the row back after commit — session.commit() expires an
    # ORM instance's attributes by default, and this function's `with`
    # block has already closed the session by the time a caller would
    # touch the returned result, so reading `row.whatever` here would
    # raise DetachedInstanceError trying to lazily re-fetch on a session
    # that's gone.
    return AuditLogEntryResult(
        entry_id=str(entry_id), actor_user_id=actor_user_id, actor_email=actor_email, org_id=org_id,
        project_id=project_id, action=action, target=target, created_at=created_at, event_metadata=event_metadata,
    )


def list_audit_events(
    engine: Engine,
    *,
    org_id: str | None = None,
    project_id: str | None = None,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLogEntryResult], int]:
    """(page, total), newest first, tiebroken on entry_id (descending) for
    the same stable-pagination reason Stage 17's other paginated lists
    (release history, alerts, notification deliveries) needed it -- an
    append-only log accumulates rows in bursts (several privileged actions
    in the same request-handling instant land in the same timestamp
    resolution) that need a deterministic second sort key."""
    with OrmSession(engine) as session:
        stmt = select(AuditLogEntry)
        if org_id is not None:
            stmt = stmt.where(AuditLogEntry.org_id == org_id)
        if project_id is not None:
            stmt = stmt.where(AuditLogEntry.project_id == project_id)
        if action is not None:
            stmt = stmt.where(AuditLogEntry.action == action)
        total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.entry_id.desc()).offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [_row_to_result(r) for r in rows], total
