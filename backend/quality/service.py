"""Stage 11 tasks 5-6: deterministic, threshold-based data-quality checks
for one project+domain, computed entirely from data already stored by
ingestion (backend.ingestion.models) and the connector run log
(backend.quality.models.ConnectorRun) — never a new source of truth,
never a heuristic guess, and never silently treating missing data as
success (a project with zero ingested sessions is reported as
"healthy" with an explicit "not_applicable" note, not silently omitted
or scored as if everything were fine).

Every threshold below is a plain constant, chosen once and documented
here — "deterministic thresholds" per the task, not learned or tunable
per call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

FRESHNESS_WARNING_HOURS = 24.0
FRESHNESS_CRITICAL_HOURS = 72.0
MISSING_OUTCOME_WARNING = 0.05
MISSING_OUTCOME_CRITICAL = 0.20
MISSING_METRIC_WARNING = 0.10
MISSING_METRIC_CRITICAL = 0.40
UNMATCHED_BUSINESS_WARNING = 0.05
UNMATCHED_BUSINESS_CRITICAL = 0.20
DUPLICATE_CONFLICT_WARNING = 0.01
DUPLICATE_CONFLICT_CRITICAL = 0.05
ARM_BALANCE_WARNING = 0.4
ARM_BALANCE_CRITICAL = 0.2
VERSION_MISSING_WARNING = 0.0
VERSION_MISSING_CRITICAL = 0.05
CONNECTOR_FAILURE_WINDOW = 20
CONNECTOR_FAILURE_WARNING = 1
CONNECTOR_FAILURE_CRITICAL = 3

STATUS_RANK = {"healthy": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class QualityCheck:
    name: str
    value: float | None
    status: str  # healthy | warning | critical | not_applicable
    detail: str


@dataclass(frozen=True)
class DataQualityReport:
    project_id: str
    domain: str
    status: str  # healthy | warning | critical
    generated_at: datetime
    checks: list[QualityCheck] = field(default_factory=list)


def _bucket(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value > warning:
        return "warning"
    return "healthy"


def _bucket_inverse(value: float, warning: float, critical: float) -> str:
    """Higher is better (a balance ratio, 1.0 = perfectly even)."""
    if value < critical:
        return "critical"
    if value < warning:
        return "warning"
    return "healthy"


def record_connector_run(
    engine: Engine,
    project_id: str,
    domain: str,
    connector: str,
    *,
    succeeded: bool,
    failure_reason: str | None = None,
    rows_fetched: int | None = None,
    matched_rows: int | None = None,
    unmatched_rows: int | None = None,
    validation_error_count: int | None = None,
) -> None:
    """Stage 11 task 5: the ONLY thing that ever writes a row here —
    called once per `import`-mode connector call (never for a dry_run),
    success or failure. backend.quality.service.compute_data_quality_report
    is the only reader."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO connector_runs (run_id, project_id, domain, connector, occurred_at, succeeded, failure_reason, "
                "rows_fetched, matched_rows, unmatched_rows, validation_error_count) "
                "VALUES (:run_id, :project_id, :domain, :connector, :occurred_at, :succeeded, :failure_reason, "
                ":rows_fetched, :matched_rows, :unmatched_rows, :validation_error_count)"
            ),
            {
                "run_id": uuid.uuid4(),
                "project_id": project_id,
                "domain": domain,
                "connector": connector,
                "occurred_at": datetime.now(timezone.utc).replace(tzinfo=None),
                "succeeded": succeeded,
                "failure_reason": failure_reason,
                "rows_fetched": rows_fetched,
                "matched_rows": matched_rows,
                "unmatched_rows": unmatched_rows,
                "validation_error_count": validation_error_count,
            },
        )


def compute_data_quality_report(engine: Engine, project_id: str, domain: str) -> DataQualityReport:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM ingested_sessions WHERE project_id = :p AND domain = :d"), {"p": project_id, "d": domain}
        ).scalar_one()

        if total == 0:
            return DataQualityReport(
                project_id=project_id,
                domain=domain,
                status="healthy",
                generated_at=now,
                checks=[
                    QualityCheck(
                        "ingested_sessions",
                        0.0,
                        "not_applicable",
                        "No sessions have been ingested into the generic pipeline yet for this project — nothing to flag.",
                    )
                ],
            )

        latest_ingested = conn.execute(
            text("SELECT max(created_at) FROM ingested_sessions WHERE project_id = :p AND domain = :d"), {"p": project_id, "d": domain}
        ).scalar_one()
        missing_outcome = conn.execute(
            text("SELECT count(*) FROM ingested_sessions WHERE project_id = :p AND domain = :d AND (outcome_label IS NULL OR outcome_label = '')"),
            {"p": project_id, "d": domain},
        ).scalar_one()
        missing_version = conn.execute(
            text("SELECT count(*) FROM ingested_sessions WHERE project_id = :p AND domain = :d AND (agent_version IS NULL OR agent_version = '')"),
            {"p": project_id, "d": domain},
        ).scalar_one()
        with_metrics = conn.execute(
            text(
                "SELECT count(DISTINCT s.session_id) FROM ingested_sessions s JOIN ingested_metrics m ON m.session_id = s.session_id "
                "WHERE s.project_id = :p AND s.domain = :d"
            ),
            {"p": project_id, "d": domain},
        ).scalar_one()
        arm_counts = dict(
            conn.execute(
                text("SELECT agent_version, count(*) FROM ingested_sessions WHERE project_id = :p AND domain = :d GROUP BY agent_version"),
                {"p": project_id, "d": domain},
            ).all()
        )
        last_business_run = conn.execute(
            text(
                "SELECT rows_fetched, unmatched_rows, validation_error_count FROM connector_runs "
                "WHERE project_id = :p AND domain = :d AND connector = 'postgres_business' AND succeeded = true "
                "ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"p": project_id, "d": domain},
        ).mappings().first()
        recent_runs = conn.execute(
            text("SELECT succeeded FROM connector_runs WHERE project_id = :p AND domain = :d ORDER BY occurred_at DESC LIMIT :n"),
            {"p": project_id, "d": domain, "n": CONNECTOR_FAILURE_WINDOW},
        ).scalars().all()

    checks: list[QualityCheck] = []

    if latest_ingested is None:
        checks.append(QualityCheck("ingestion_freshness_hours", None, "not_applicable", "no timestamped ingestion found"))
    else:
        age_hours = (now - latest_ingested).total_seconds() / 3600.0
        checks.append(
            QualityCheck(
                "ingestion_freshness_hours",
                age_hours,
                _bucket(age_hours, FRESHNESS_WARNING_HOURS, FRESHNESS_CRITICAL_HOURS),
                f"most recently ingested session is {age_hours:.1f}h old",
            )
        )

    missing_outcome_rate = missing_outcome / total
    checks.append(
        QualityCheck(
            "missing_outcome_rate",
            missing_outcome_rate,
            _bucket(missing_outcome_rate, MISSING_OUTCOME_WARNING, MISSING_OUTCOME_CRITICAL),
            f"{missing_outcome}/{total} sessions have no outcome label",
        )
    )

    missing_metric_rate = 1.0 - (with_metrics / total)
    checks.append(
        QualityCheck(
            "missing_metric_coverage_rate",
            missing_metric_rate,
            _bucket(missing_metric_rate, MISSING_METRIC_WARNING, MISSING_METRIC_CRITICAL),
            f"{total - with_metrics}/{total} sessions have no metrics recorded at all",
        )
    )

    missing_version_rate = missing_version / total
    checks.append(
        QualityCheck(
            "sessions_without_version_rate",
            missing_version_rate,
            _bucket(missing_version_rate, VERSION_MISSING_WARNING, VERSION_MISSING_CRITICAL),
            f"{missing_version}/{total} sessions have no agent_version",
        )
    )

    non_null_arms = {k: v for k, v in arm_counts.items() if k}
    if len(non_null_arms) < 2 or any(v == 0 for v in non_null_arms.values()):
        checks.append(
            QualityCheck(
                "experiment_arm_balance_ratio",
                0.0 if non_null_arms else None,
                "critical" if non_null_arms else "not_applicable",
                f"agent_version counts: {non_null_arms or 'none'} — need at least two non-empty arms to compare",
            )
        )
    else:
        values = sorted(non_null_arms.values())
        ratio = values[0] / values[-1]
        checks.append(
            QualityCheck(
                "experiment_arm_balance_ratio",
                ratio,
                _bucket_inverse(ratio, ARM_BALANCE_WARNING, ARM_BALANCE_CRITICAL),
                f"agent_version counts: {non_null_arms}",
            )
        )

    if last_business_run is None:
        checks.append(QualityCheck("unmatched_business_data_rate", None, "not_applicable", "no Postgres business-data enrichment has run yet"))
        checks.append(QualityCheck("duplicate_conflict_rate", None, "not_applicable", "no Postgres business-data enrichment has run yet"))
    else:
        fetched = last_business_run["rows_fetched"] or 0
        unmatched = last_business_run["unmatched_rows"] or 0
        conflicts = last_business_run["validation_error_count"] or 0
        unmatched_rate = (unmatched / fetched) if fetched else 0.0
        conflict_rate = (conflicts / fetched) if fetched else 0.0
        checks.append(
            QualityCheck(
                "unmatched_business_data_rate",
                unmatched_rate,
                _bucket(unmatched_rate, UNMATCHED_BUSINESS_WARNING, UNMATCHED_BUSINESS_CRITICAL),
                f"{unmatched}/{fetched} business rows unmatched in the most recent enrichment run",
            )
        )
        checks.append(
            QualityCheck(
                "duplicate_conflict_rate",
                conflict_rate,
                _bucket(conflict_rate, DUPLICATE_CONFLICT_WARNING, DUPLICATE_CONFLICT_CRITICAL),
                f"{conflicts}/{fetched} conflicting/invalid rows in the most recent enrichment run",
            )
        )

    if not recent_runs:
        checks.append(QualityCheck("connector_import_failure_count", None, "not_applicable", "no connector runs recorded yet"))
    else:
        failures = sum(1 for s in recent_runs if not s)
        status = "critical" if failures >= CONNECTOR_FAILURE_CRITICAL else "warning" if failures >= CONNECTOR_FAILURE_WARNING else "healthy"
        checks.append(
            QualityCheck(
                "connector_import_failure_count",
                float(failures),
                status,
                f"{failures} failed connector run(s) out of the last {len(recent_runs)} recorded",
            )
        )

    evaluated = [c.status for c in checks if c.status != "not_applicable"]
    overall = max(evaluated, key=lambda s: STATUS_RANK[s]) if evaluated else "healthy"

    return DataQualityReport(project_id=project_id, domain=domain, status=overall, generated_at=now, checks=checks)
