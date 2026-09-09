"""Stage 11 tasks 1-2: monitoring job configuration, execution, and
history. A job here means "run backend.release.service.evaluate_and_
persist_release for this (project, domain, experiment, primary_metric)
and record what happened" — no new evaluation or decision logic; the
SAME entry point the on-demand release-evaluations API endpoint already
uses (Stage 11 task 8: existing release logic stays unchanged).

Concurrency (task 2, "prevent duplicate concurrent runs"): a Postgres
advisory lock keyed by (project_id, experiment_id) is held on a
dedicated connection for the duration of one run — correct across
multiple worker processes, not just threads within one, and needs no
in-process-only state.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.monitoring.models import MonitoringConfig, MonitoringRun


@dataclass(frozen=True)
class MonitoringConfigResult:
    config_id: str
    project_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    cadence_seconds: int
    window_hours: int | None
    enabled: bool
    created_at: datetime


@dataclass(frozen=True)
class MonitoringRunResult:
    run_id: str
    config_id: str | None
    project_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    status: str  # running | succeeded | failed | skipped_duplicate
    started_at: datetime
    completed_at: datetime | None
    data_window_start: datetime | None
    data_window_end: datetime | None
    release_evaluation_id: str | None
    failure_reason: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _config_to_result(row: MonitoringConfig) -> MonitoringConfigResult:
    return MonitoringConfigResult(
        config_id=str(row.config_id), project_id=row.project_id, domain=row.domain, experiment_id=row.experiment_id,
        primary_metric=row.primary_metric, cadence_seconds=row.cadence_seconds, window_hours=row.window_hours,
        enabled=row.enabled, created_at=row.created_at,
    )


def _run_to_result(row: MonitoringRun) -> MonitoringRunResult:
    return MonitoringRunResult(
        run_id=str(row.run_id), config_id=str(row.config_id) if row.config_id else None, project_id=row.project_id,
        domain=row.domain, experiment_id=row.experiment_id, primary_metric=row.primary_metric, status=row.status,
        started_at=row.started_at, completed_at=row.completed_at, data_window_start=row.data_window_start,
        data_window_end=row.data_window_end, release_evaluation_id=row.release_evaluation_id, failure_reason=row.failure_reason,
    )


def create_monitoring_config(
    engine: Engine, project_id: str, domain: str, experiment_id: str, primary_metric: str,
    cadence_seconds: int, window_hours: int | None = None, enabled: bool = True,
) -> MonitoringConfigResult:
    row = MonitoringConfig(
        config_id=uuid.uuid4(), project_id=project_id, domain=domain, experiment_id=experiment_id,
        primary_metric=primary_metric, cadence_seconds=cadence_seconds, window_hours=window_hours,
        enabled=enabled, created_at=_now(),
    )
    with OrmSession(engine) as session:
        session.add(row)
        session.commit()
        return _config_to_result(row)


def list_monitoring_configs(engine: Engine, project_id: str) -> list[MonitoringConfigResult]:
    with OrmSession(engine) as session:
        rows = session.query(MonitoringConfig).filter(MonitoringConfig.project_id == project_id).order_by(MonitoringConfig.created_at.desc()).all()
        return [_config_to_result(r) for r in rows]


def get_monitoring_config(engine: Engine, project_id: str, config_id: str) -> MonitoringConfigResult | None:
    with OrmSession(engine) as session:
        row = session.query(MonitoringConfig).filter(MonitoringConfig.project_id == project_id, MonitoringConfig.config_id == uuid.UUID(config_id)).first()
        return _config_to_result(row) if row else None


def _lock_key(project_id: str, experiment_id: str) -> int:
    # A 32-bit key fits pg_try_advisory_lock's bigint parameter and, using
    # zlib.crc32 rather than Python's own (per-process-randomized) hash(),
    # is identical across processes -- required for the lock to actually
    # serialize concurrent runs from two different worker processes.
    return zlib.crc32(f"{project_id}:{experiment_id}".encode())


def run_monitoring_job(engine: Engine, config: MonitoringConfigResult, adapter_factory) -> MonitoringRunResult:
    """adapter_factory(domain, project_id) -> DomainAdapter, injected so
    this module (backend.monitoring, a sibling of backend.release) never
    imports backend.app.domain_registry or a concrete domain package."""
    from backend.release.service import evaluate_and_persist_release

    started_at = _now()
    window_start = started_at - timedelta(hours=config.window_hours) if config.window_hours else None
    run_id = uuid.uuid4()
    key = _lock_key(config.project_id, config.experiment_id)

    conn = engine.connect()
    try:
        acquired = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        if not acquired:
            reason = "another monitoring run for this project/experiment is already in progress"
            with OrmSession(engine) as session:
                row = MonitoringRun(
                    run_id=run_id, config_id=uuid.UUID(config.config_id), project_id=config.project_id, domain=config.domain,
                    experiment_id=config.experiment_id, primary_metric=config.primary_metric, status="skipped_duplicate",
                    started_at=started_at, completed_at=started_at, data_window_start=window_start, data_window_end=started_at,
                    release_evaluation_id=None, failure_reason=reason,
                )
                session.add(row)
                session.commit()
                return _run_to_result(row)

        with OrmSession(engine) as session:
            row = MonitoringRun(
                run_id=run_id, config_id=uuid.UUID(config.config_id), project_id=config.project_id, domain=config.domain,
                experiment_id=config.experiment_id, primary_metric=config.primary_metric, status="running",
                started_at=started_at, completed_at=None, data_window_start=window_start, data_window_end=started_at,
                release_evaluation_id=None, failure_reason=None,
            )
            session.add(row)
            session.commit()

        try:
            adapter = adapter_factory(config.domain, config.project_id)
            result = evaluate_and_persist_release(engine, config.domain, config.experiment_id, adapter, config.primary_metric, project_id=config.project_id)
            completed_at = _now()
            with OrmSession(engine) as session:
                session.query(MonitoringRun).filter(MonitoringRun.run_id == run_id).update(
                    {"status": "succeeded", "completed_at": completed_at, "release_evaluation_id": result.evaluation_id}
                )
                session.commit()
                updated = session.query(MonitoringRun).filter(MonitoringRun.run_id == run_id).one()
                return _run_to_result(updated)
        except Exception as exc:
            completed_at = _now()
            reason = str(exc)
            with OrmSession(engine) as session:
                session.query(MonitoringRun).filter(MonitoringRun.run_id == run_id).update({"status": "failed", "completed_at": completed_at, "failure_reason": reason})
                session.commit()
                updated = session.query(MonitoringRun).filter(MonitoringRun.run_id == run_id).one()
                return _run_to_result(updated)
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        except Exception:
            pass
        conn.close()


def list_due_configs(engine: Engine) -> list[MonitoringConfigResult]:
    """Enabled configs that have never run, or whose cadence has elapsed
    since their last (non-duplicate-skipped) run — the scheduler's own
    poll loop calls this."""
    with OrmSession(engine) as session:
        configs = session.query(MonitoringConfig).filter(MonitoringConfig.enabled.is_(True)).all()
        now = _now()
        due: list[MonitoringConfig] = []
        for c in configs:
            last_run = (
                session.query(MonitoringRun)
                .filter(MonitoringRun.config_id == c.config_id, MonitoringRun.status.in_(["succeeded", "failed"]))
                .order_by(MonitoringRun.started_at.desc())
                .first()
            )
            if last_run is None or (now - last_run.started_at).total_seconds() >= c.cadence_seconds:
                due.append(c)
        return [_config_to_result(c) for c in due]


def list_monitoring_runs(engine: Engine, project_id: str, config_id: str, limit: int = 20) -> list[MonitoringRunResult]:
    with OrmSession(engine) as session:
        rows = (
            session.query(MonitoringRun)
            .filter(MonitoringRun.project_id == project_id, MonitoringRun.config_id == uuid.UUID(config_id))
            .order_by(MonitoringRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [_run_to_result(r) for r in rows]


def get_latest_monitoring_run(engine: Engine, project_id: str, config_id: str) -> MonitoringRunResult | None:
    with OrmSession(engine) as session:
        row = (
            session.query(MonitoringRun)
            .filter(MonitoringRun.project_id == project_id, MonitoringRun.config_id == uuid.UUID(config_id))
            .order_by(MonitoringRun.started_at.desc())
            .first()
        )
        return _run_to_result(row) if row else None
