"""Postgres business-data enrichment orchestration (Stage 10 tasks 1/3/4):
fetch rows from the customer's Postgres, resolve duplicates, join them to
already-ingested sessions in the CALLER'S project by explicit configured
keys (never guessed), and either preview the result (dry run — no
database write) or persist the mapped metrics through the existing
generic upsert path (backend.ingestion.service.upsert_metrics) — the
exact same table and idempotency semantics ingest_batch itself uses.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.connectors.postgres_business.client import PostgresBusinessClient
from backend.connectors.postgres_business.mapper import TypeMismatchError, ValidationIssue, coerce_value, dedupe_rows
from backend.connectors.postgres_business.schemas import (
    PostgresEnrichmentPreview,
    PostgresEnrichmentRequest,
    PostgresEnrichmentResult,
    PostgresUnmatchedRow,
)
from backend.ingestion.service import metric_id_for, upsert_metrics


class JoinConfigError(Exception):
    """The configured join_key_column (or a mapped metric's source_column)
    doesn't exist in the fetched rows at all — a configuration mistake,
    reported once for the whole batch rather than treated as a per-row
    unmatched/validation case."""


def _project_sessions(engine: Engine, project_id: str, domain: str, join_key_target: str) -> dict[str, list[tuple[str, str]]]:
    """{join key value -> [(session_id, external_session_id), ...]} for
    every session already ingested into this project+domain. Tenancy is
    the WHERE clause: a business source can never enrich a session
    outside the caller's own project (Stage 10 task 5)."""
    key_column = "external_user_id" if join_key_target == "external_user_id" else "external_session_id"
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT session_id, external_session_id, {key_column} AS join_key FROM ingested_sessions WHERE project_id = :pid AND domain = :domain"),
            {"pid": project_id, "domain": domain},
        ).mappings().all()

    index: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        if row["join_key"] is None:
            continue
        index.setdefault(str(row["join_key"]), []).append((str(row["session_id"]), row["external_session_id"]))
    return index


def _all_external_session_ids(engine: Engine, project_id: str, domain: str) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT external_session_id FROM ingested_sessions WHERE project_id = :pid AND domain = :domain"),
                {"pid": project_id, "domain": domain},
            ).scalars()
        )


def _build_plan(engine: Engine, project_id: str, request: PostgresEnrichmentRequest, rows: list[dict]):
    source = request.source
    join_col = source.join.join_key_column
    if rows and join_col not in rows[0]:
        raise JoinConfigError(f"join_key_column {join_col!r} is not a column in the source data — never guessing which column to join on")
    for m in source.metrics:
        if rows and m.source_column not in rows[0]:
            raise JoinConfigError(f"mapped source_column {m.source_column!r} is not a column in the source data")

    deduped, dup_issues = dedupe_rows(rows, source)
    sessions_by_key = _project_sessions(engine, project_id, request.domain, source.join.join_key_target)

    metric_rows: list[dict] = []
    metrics_preview: list[dict] = []
    unmatched: list[PostgresUnmatchedRow] = []
    validation_errors: list[ValidationIssue] = list(dup_issues)
    null_values_skipped = 0
    matched_row_count = 0
    matched_external_session_ids: set[str] = set()

    for row in deduped:
        key_value = row.get(join_col)
        key_str = str(key_value) if key_value is not None else None
        if key_value is None or key_str == "":
            unmatched.append(PostgresUnmatchedRow(join_key_value=None, reason=f"row has no value in join_key_column {join_col!r}"))
            continue

        matches = sessions_by_key.get(key_str)
        if not matches:
            unmatched.append(PostgresUnmatchedRow(join_key_value=key_str, reason=f"no ingested session in this project found for {source.join.join_key_target}={key_str!r}"))
            continue

        matched_row_count += 1
        for session_id, external_session_id in matches:
            matched_external_session_ids.add(external_session_id)
            for m in source.metrics:
                raw = row.get(m.source_column)
                try:
                    value = coerce_value(raw, m.value_type)
                except TypeMismatchError as exc:
                    validation_errors.append(ValidationIssue(join_key_value=key_str, column=m.source_column, message=str(exc)))
                    continue
                if value is None:
                    null_values_skipped += 1
                    continue
                metric_rows.append(
                    {
                        "metric_id": metric_id_for(project_id, request.domain, external_session_id, m.metric_name),
                        "session_id": session_id,
                        "name": m.metric_name,
                        "value": value,
                    }
                )
                metrics_preview.append({"external_session_id": external_session_id, "name": m.metric_name, "value": value})

    all_session_ids = _all_external_session_ids(engine, project_id, request.domain)
    sessions_with_no_match = sorted(all_session_ids - matched_external_session_ids)

    return metric_rows, metrics_preview, unmatched, validation_errors, null_values_skipped, matched_row_count, sessions_with_no_match


def preview_enrichment(engine: Engine, client: PostgresBusinessClient, project_id: str, request: PostgresEnrichmentRequest) -> PostgresEnrichmentPreview:
    rows = client.fetch_rows(request.source)
    metric_rows, metrics_preview, unmatched, validation_errors, nulls_skipped, matched_rows, sessions_with_no_match = _build_plan(engine, project_id, request, rows)
    return PostgresEnrichmentPreview(
        domain=request.domain,
        source_rows_fetched=len(rows),
        matched_rows=matched_rows,
        unmatched_source_rows=unmatched,
        sessions_with_no_match=sessions_with_no_match,
        mapped_metrics_preview=metrics_preview[:20],
        validation_errors=[e.__dict__ for e in validation_errors],
        null_values_skipped=nulls_skipped,
    )


def run_enrichment(engine: Engine, client: PostgresBusinessClient, project_id: str, request: PostgresEnrichmentRequest) -> PostgresEnrichmentResult:
    rows = client.fetch_rows(request.source)
    metric_rows, _preview, unmatched, validation_errors, nulls_skipped, matched_rows, sessions_with_no_match = _build_plan(engine, project_id, request, rows)
    persisted = upsert_metrics(engine, metric_rows)
    return PostgresEnrichmentResult(
        domain=request.domain,
        source_rows_fetched=len(rows),
        matched_rows=matched_rows,
        metrics_persisted=persisted,
        unmatched_source_rows=unmatched,
        sessions_with_no_match=sessions_with_no_match,
        validation_errors=[e.__dict__ for e in validation_errors],
        null_values_skipped=nulls_skipped,
    )
