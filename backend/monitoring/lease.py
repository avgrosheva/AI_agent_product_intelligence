"""Stage 18 task 5: database-backed lease so only ONE backend instance's
MonitoringScheduler thread actually polls for due jobs at a time, even
when several instances run the same process. See
backend.monitoring.models.SchedulerLease for the full rationale (short
version: this stops redundant polling and makes "who's leading" visible;
backend.monitoring.service.run_monitoring_job's existing per-job Postgres
advisory lock remains the actual, independent guarantee that a due job
never executes twice).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class LeaseState:
    lease_key: str
    holder_id: str
    acquired_at: datetime
    expires_at: datetime

    @property
    def is_active(self) -> bool:
        return self.expires_at > _now()


def try_acquire_or_renew_lease(engine: Engine, lease_key: str, holder_id: str, ttl_seconds: float) -> bool:
    """Atomic: succeeds if no lease row exists yet, the existing one has
    expired, or `holder_id` already holds it (a renewal). One SQL
    statement inside one transaction, race-free across processes even
    without an explicit app-level lock — the UNIQUE constraint on
    lease_key (its primary key) is what Postgres uses to serialize
    concurrent INSERTs, and the WHERE clause on the DO UPDATE branch is
    what stops a second instance from stealing a lease that's still
    live and held by someone else."""
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO scheduler_leases (lease_key, holder_id, acquired_at, expires_at) "
                "VALUES (:lease_key, :holder_id, :now, :expires_at) "
                "ON CONFLICT (lease_key) DO UPDATE SET holder_id = :holder_id, acquired_at = :now, expires_at = :expires_at "
                "WHERE scheduler_leases.expires_at < :now OR scheduler_leases.holder_id = :holder_id"
            ),
            {"lease_key": lease_key, "holder_id": holder_id, "now": now, "expires_at": expires_at},
        )
        return result.rowcount > 0


def release_lease(engine: Engine, lease_key: str, holder_id: str) -> None:
    """Best-effort, called on clean scheduler shutdown so another instance
    doesn't have to wait out the full TTL before taking over. Only
    releases if this holder still actually owns it -- never clobbers a
    lease acquired by someone else in the meantime (e.g. this instance's
    own lease already expired and was reclaimed before shutdown ran)."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM scheduler_leases WHERE lease_key = :lease_key AND holder_id = :holder_id"),
            {"lease_key": lease_key, "holder_id": holder_id},
        )


def get_lease_state(engine: Engine, lease_key: str) -> LeaseState | None:
    """Read-only — used by the operational health endpoint
    (backend.app.routers.ops) to report which instance is currently
    leading the monitoring scheduler, and whether that lease is still
    live or has lapsed with nobody yet having renewed it."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT lease_key, holder_id, acquired_at, expires_at FROM scheduler_leases WHERE lease_key = :lease_key"),
            {"lease_key": lease_key},
        ).mappings().first()
    if row is None:
        return None
    return LeaseState(lease_key=row["lease_key"], holder_id=row["holder_id"], acquired_at=row["acquired_at"], expires_at=row["expires_at"])
