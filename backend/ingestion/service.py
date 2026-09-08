"""Ingestion service: business validation beyond Pydantic's schema check,
and idempotent persistence into the generic storage tables
(backend.ingestion.models). One batch is ingested atomically — either
every row lands, or a validation error is raised before anything is
written (no partial-batch state).

Idempotency: every row's primary key is a deterministic UUID5 derived
from (domain, external ids) — see `_id` below — and every insert is an
`INSERT ... ON CONFLICT (...) DO UPDATE`, so re-sending the same batch
(identical or corrected) converges to the same end state rather than
duplicating or erroring.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.ingestion.models import (
    IngestedAction,
    IngestedExperiment,
    IngestedMessage,
    IngestedMetric,
    IngestedSession,
    IngestedToolCall,
)
from backend.ingestion.schemas import IngestBatchRequest, IngestionErrorDetail, IngestionResponse

_NAMESPACE = uuid.UUID("c9e1a2b3-8f4e-4a11-9b7d-1f2e3d4c5b6a")


def _id(domain: str, *parts: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, ":".join((domain, *parts)))


class IngestionValidationError(Exception):
    def __init__(self, errors: list[IngestionErrorDetail]):
        self.errors = errors
        super().__init__("; ".join(e.message for e in errors))


def _validate_experiment_references(engine: Engine, request: IngestBatchRequest) -> None:
    batch_experiment_ids = {e.external_experiment_id for e in request.experiments}
    needed = {s.external_experiment_id for s in request.sessions} - batch_experiment_ids
    existing: set[str] = set()
    if needed:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT external_experiment_id FROM ingested_experiments "
                    "WHERE domain = :domain AND external_experiment_id = ANY(:ids)"
                ),
                {"domain": request.domain, "ids": list(needed)},
            ).scalars().all()
        existing = set(rows)

    known = batch_experiment_ids | existing
    errors: list[IngestionErrorDetail] = []
    for i, session in enumerate(request.sessions):
        if session.external_experiment_id not in known:
            errors.append(
                IngestionErrorDetail(
                    session_index=i,
                    external_session_id=session.external_session_id,
                    message=(
                        f"references unknown external_experiment_id "
                        f"{session.external_experiment_id!r} (not in this batch's `experiments` "
                        f"and not previously ingested for domain {request.domain!r})"
                    ),
                )
            )
    if errors:
        raise IngestionValidationError(errors)


def ingest_batch(engine: Engine, request: IngestBatchRequest) -> IngestionResponse:
    _validate_experiment_references(engine, request)

    domain = request.domain
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    experiment_rows = [
        {
            "experiment_id": _id(domain, "experiment", e.external_experiment_id),
            "domain": domain,
            "external_experiment_id": e.external_experiment_id,
            "name": e.name,
            "control_version": e.control_version,
            "treatment_version": e.treatment_version,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "created_at": now,
        }
        for e in request.experiments
    ]

    session_rows, message_rows, action_rows, tool_call_rows, metric_rows = [], [], [], [], []

    for session in request.sessions:
        session_id = _id(domain, "session", session.external_session_id)
        experiment_id = _id(domain, "experiment", session.external_experiment_id)

        session_rows.append(
            {
                "session_id": session_id,
                "domain": domain,
                "external_session_id": session.external_session_id,
                "experiment_id": experiment_id,
                "agent_version": session.agent_version,
                "external_user_id": session.external_user_id,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "outcome_label": session.outcome.label,
                "context": session.context,
                "created_at": now,
            }
        )

        for m in session.messages:
            message_rows.append(
                {
                    "message_id": _id(domain, "message", session.external_session_id, m.external_message_id),
                    "session_id": session_id,
                    "external_message_id": m.external_message_id,
                    "turn_index": m.turn_index,
                    "sender": m.sender,
                    "text": m.text,
                    "created_at": m.created_at,
                }
            )

        for a in session.actions:
            action_id = _id(domain, "action", session.external_session_id, a.external_action_id)
            action_rows.append(
                {
                    "action_id": action_id,
                    "session_id": session_id,
                    "external_action_id": a.external_action_id,
                    "sequence_index": a.sequence_index,
                    "action_type": a.action_type,
                    "started_at": a.started_at,
                    "latency_ms": a.latency_ms,
                }
            )
            for tc in a.tool_calls:
                tool_call_rows.append(
                    {
                        "tool_call_id": _id(domain, "toolcall", session.external_session_id, a.external_action_id, tc.external_tool_call_id),
                        "action_id": action_id,
                        "session_id": session_id,
                        "external_tool_call_id": tc.external_tool_call_id,
                        "tool_name": tc.tool_name,
                        "success": tc.success,
                        "error_type": tc.error_type,
                        "latency_ms": tc.latency_ms,
                        "input_json": tc.input,
                        "output_json": tc.output,
                    }
                )

        # Session-level metrics take precedence over same-named outcome
        # metrics (last-write-wins on a per-session, per-name basis) —
        # both are just (name, value) pairs from the contract's point of
        # view, so a name collision is resolved by write order, not an error.
        merged_metrics: dict[str, float] = {m.name: m.value for m in session.outcome.metrics}
        merged_metrics.update({m.name: m.value for m in session.metrics})
        for name, value in merged_metrics.items():
            metric_rows.append(
                {
                    "metric_id": _id(domain, "metric", session.external_session_id, name),
                    "session_id": session_id,
                    "name": name,
                    "value": value,
                }
            )

    with OrmSession(engine) as db:
        if experiment_rows:
            stmt = pg_insert(IngestedExperiment).values(experiment_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["domain", "external_experiment_id"],
                set_={c: stmt.excluded[c] for c in ("name", "control_version", "treatment_version", "start_date", "end_date")},
            )
            db.execute(stmt)

        if session_rows:
            stmt = pg_insert(IngestedSession).values(session_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["domain", "external_session_id"],
                set_={c: stmt.excluded[c] for c in ("experiment_id", "agent_version", "external_user_id", "started_at", "ended_at", "outcome_label", "context")},
            )
            db.execute(stmt)

        if message_rows:
            stmt = pg_insert(IngestedMessage).values(message_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id", "external_message_id"],
                set_={c: stmt.excluded[c] for c in ("turn_index", "sender", "text", "created_at")},
            )
            db.execute(stmt)

        if action_rows:
            stmt = pg_insert(IngestedAction).values(action_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id", "external_action_id"],
                set_={c: stmt.excluded[c] for c in ("sequence_index", "action_type", "started_at", "latency_ms")},
            )
            db.execute(stmt)

        if tool_call_rows:
            stmt = pg_insert(IngestedToolCall).values(tool_call_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["action_id", "external_tool_call_id"],
                set_={c: stmt.excluded[c] for c in ("tool_name", "success", "error_type", "latency_ms", "input_json", "output_json")},
            )
            db.execute(stmt)

        if metric_rows:
            stmt = pg_insert(IngestedMetric).values(metric_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id", "name"],
                set_={"value": stmt.excluded["value"]},
            )
            db.execute(stmt)

        db.commit()

    return IngestionResponse(
        domain=domain,
        experiments_ingested=len(experiment_rows),
        sessions_ingested=len(session_rows),
        messages_ingested=len(message_rows),
        actions_ingested=len(action_rows),
        tool_calls_ingested=len(tool_call_rows),
        metrics_ingested=len(metric_rows),
    )
