"""Pure logic for the Postgres business-data connector (Stage 10 tasks
3/6): coercing a raw source-row value to the mapped metric's declared
type, and resolving duplicate source rows for the same join key. No
database, no HTTP — every function here takes plain dicts/values and
returns plain dataclasses, so it is testable without a real Postgres
connection (the join against ingested_sessions itself needs the database
and lives in backend.connectors.postgres_business.service instead).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.connectors.postgres_business.schemas import PostgresMetricMapping, PostgresSourceConfig

_TRUE_STRINGS = {"true", "t", "yes", "y", "1"}
_FALSE_STRINGS = {"false", "f", "no", "n", "0"}


class TypeMismatchError(Exception):
    pass


@dataclass(frozen=True)
class ValidationIssue:
    join_key_value: str | None
    column: str | None
    message: str


def coerce_value(raw: object, value_type: str) -> float | None:
    """None passes through untouched (a genuine NULL — the caller skips
    it, never fabricating a value). Anything else is coerced to the
    mapped metric's declared type or raises TypeMismatchError — never
    silently coerced to a default like 0."""
    if raw is None:
        return None
    if value_type == "boolean":
        if isinstance(raw, bool):
            return 1.0 if raw else 0.0
        if isinstance(raw, (int, float)) and raw in (0, 1):
            return float(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in _TRUE_STRINGS:
                return 1.0
            if lowered in _FALSE_STRINGS:
                return 0.0
        raise TypeMismatchError(f"cannot interpret {raw!r} as a boolean")
    # numeric
    if isinstance(raw, bool):  # bool is an int subclass -- reject before the int/float branch
        raise TypeMismatchError(f"cannot interpret {raw!r} as numeric")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            raise TypeMismatchError(f"cannot interpret {raw!r} as numeric") from None
    try:
        return float(raw)  # e.g. decimal.Decimal
    except (TypeError, ValueError):
        raise TypeMismatchError(f"cannot interpret {raw!r} as numeric") from None


def _row_metric_values(row: dict, metrics: list[PostgresMetricMapping]) -> tuple:
    return tuple(row.get(m.source_column) for m in metrics)


def dedupe_rows(rows: list[dict], source: PostgresSourceConfig) -> tuple[list[dict], list[ValidationIssue]]:
    """Groups rows by the configured join key. A single row per key needs
    no resolution. Multiple rows for the same key are resolved by
    `timestamp_column` (most recent wins) when configured; otherwise,
    exact duplicates (identical values in every mapped metric column) are
    harmless and collapse silently, but genuinely conflicting duplicate
    rows are never guessed at — they're reported as a validation issue
    and none of them are used."""
    join_col = source.join.join_key_column
    groups: dict[object, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get(join_col), []).append(row)

    resolved: list[dict] = []
    issues: list[ValidationIssue] = []
    for key, group in groups.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        if source.join.timestamp_column:
            ts_col = source.join.timestamp_column
            timestamped = [(r, r.get(ts_col)) for r in group]
            if all(ts is not None for _, ts in timestamped):
                parsed = [(r, ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))) for r, ts in timestamped]
                winner = max(parsed, key=lambda pair: pair[1])[0]
                resolved.append(winner)
                continue

        distinct_value_sets = {_row_metric_values(r, source.metrics) for r in group}
        if len(distinct_value_sets) == 1:
            resolved.append(group[0])  # exact duplicates -- harmless, dedupe silently
            continue

        issues.append(
            ValidationIssue(
                join_key_value=str(key) if key is not None else None,
                column=join_col,
                message=f"{len(group)} rows share join key {key!r} with conflicting values and no usable timestamp_column to break the tie — none were used",
            )
        )

    return resolved, issues
