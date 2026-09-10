"""Stage 12 tasks 4-5: read/write persisted project configuration, and
validate a candidate configuration before it's saved. This module never
imports a concrete domain package (backend.domains.commerce/support) —
the caller (backend.app.routers.domains, the composition root for the
generic API) supplies whatever domain-specific context validation needs
(the effective set of metric names, and which context keys ingested data
actually has), matching this project's established "core doesn't know
about domains" architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.core.config import load_guardrail_config_from_dict, load_metric_config_from_dict
from backend.project_config.models import ProjectConfig

VALID_EVENT_TYPES = {"ROLLBACK", "HOLD", "BLOCKING_GUARDRAIL_BREACH", "CRITICAL_DATA_QUALITY", "MONITORING_JOB_FAILURE"}


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ProjectConfigResult:
    project_id: str
    primary_metric: str | None
    metrics: dict | None
    guardrails: dict | None
    segment_dimensions: dict | None
    economics: dict | None
    monitoring_cadence_seconds: int | None
    enabled_notification_rules: list[str]
    created_at: datetime
    updated_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_result(row: ProjectConfig) -> ProjectConfigResult:
    return ProjectConfigResult(
        project_id=row.project_id, primary_metric=row.primary_metric, metrics=row.metrics_json,
        guardrails=row.guardrails_json, segment_dimensions=row.segment_dimensions_json, economics=row.economics_json,
        monitoring_cadence_seconds=row.monitoring_cadence_seconds, enabled_notification_rules=row.enabled_notification_rules or [],
        created_at=row.created_at, updated_at=row.updated_at,
    )


def get_project_config(engine: Engine, project_id: str) -> ProjectConfigResult | None:
    with OrmSession(engine) as session:
        row = session.get(ProjectConfig, project_id)
        return _to_result(row) if row is not None else None


def existing_context_keys(engine: Engine, project_id: str, domain: str) -> set[str]:
    """Stage 12 task 5: "segment dimensions must exist in available
    context/data" — the actual JSON keys seen across this project's own
    ingested session context, so far. Empty when no data has arrived yet
    (validation treats that as "can't check yet", never as a hard error —
    a project shouldn't be blocked from configuring segments before its
    first ingest)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT context FROM ingested_sessions WHERE project_id = :p AND domain = :d AND context IS NOT NULL LIMIT 500"),
            {"p": project_id, "d": domain},
        ).scalars().all()
    keys: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            keys.update(row.keys())
    return keys


def validate_project_config(
    *,
    primary_metric: str | None,
    metrics_json: dict | None,
    guardrails_json: dict | None,
    segment_dimensions_json: dict | None,
    economics_json: dict | None,
    enabled_notification_rules: list[str] | None,
    effective_metric_names: set[str],
    known_context_keys: set[str],
) -> list[ValidationIssue]:
    """`effective_metric_names` is whatever metric names WILL be in effect
    once this config is saved — the caller computes it (parsing
    metrics_json here itself, when provided, else the domain's current
    adapter.metric_definitions()) so this function stays domain-agnostic.
    `known_context_keys` is empty when the project has no ingested data
    yet — see existing_context_keys()."""
    issues: list[ValidationIssue] = []

    if metrics_json is not None:
        try:
            load_metric_config_from_dict(metrics_json)
        except (KeyError, ValueError, TypeError) as exc:
            issues.append(ValidationIssue("metrics", f"invalid metrics config: {exc}"))

    if guardrails_json is not None:
        try:
            guardrails = load_guardrail_config_from_dict(guardrails_json)
        except (KeyError, ValueError, TypeError) as exc:
            issues.append(ValidationIssue("guardrails", f"invalid guardrails config: {exc}"))
        else:
            for g in guardrails:
                if g.metric and effective_metric_names and g.metric not in effective_metric_names:
                    issues.append(ValidationIssue("guardrails", f"guardrail {g.name!r} references unknown metric {g.metric!r}"))

    if segment_dimensions_json is not None:
        if not isinstance(segment_dimensions_json, dict):
            issues.append(ValidationIssue("segment_dimensions", "must be an object of dimension_name -> [allowed values]"))
        else:
            for dim in segment_dimensions_json:
                if known_context_keys and dim not in known_context_keys:
                    issues.append(ValidationIssue("segment_dimensions", f"dimension {dim!r} was not found in any ingested session's context yet"))

    if primary_metric is not None and effective_metric_names and primary_metric not in effective_metric_names:
        issues.append(ValidationIssue("primary_metric", f"'{primary_metric}' is not one of the configured metrics {sorted(effective_metric_names)}"))

    if economics_json is not None:
        if not economics_json.get("success_column"):
            issues.append(ValidationIssue("economics", "success_column is required when an economics mapping is provided"))

    if enabled_notification_rules is not None:
        unknown = set(enabled_notification_rules) - VALID_EVENT_TYPES
        if unknown:
            issues.append(ValidationIssue("enabled_notification_rules", f"unknown event type(s) {sorted(unknown)} — must be one of {sorted(VALID_EVENT_TYPES)}"))

    return issues


def upsert_project_config(
    engine: Engine,
    project_id: str,
    *,
    primary_metric: str | None,
    metrics_json: dict | None,
    guardrails_json: dict | None,
    segment_dimensions_json: dict | None,
    economics_json: dict | None,
    monitoring_cadence_seconds: int | None,
    enabled_notification_rules: list[str] | None,
) -> ProjectConfigResult:
    now = _now()
    with OrmSession(engine) as session:
        row = session.get(ProjectConfig, project_id)
        if row is None:
            row = ProjectConfig(project_id=project_id, created_at=now)
            session.add(row)
        row.primary_metric = primary_metric
        row.metrics_json = metrics_json
        row.guardrails_json = guardrails_json
        row.segment_dimensions_json = segment_dimensions_json
        row.economics_json = economics_json
        row.monitoring_cadence_seconds = monitoring_cadence_seconds
        row.enabled_notification_rules = enabled_notification_rules or []
        row.updated_at = now
        session.commit()
        return _to_result(row)
