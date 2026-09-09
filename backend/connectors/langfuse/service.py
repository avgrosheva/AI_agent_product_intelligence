"""Langfuse import orchestration (Stage 9 tasks 1/3): fetch traces for a
project/time range from Langfuse, map them into this platform's generic
ingestion schema (backend.ingestion.schemas), and either preview the
result (dry run — no database write) or hand the batch to the existing,
already-idempotent backend.ingestion.service.ingest_batch — the exact
same entry point any other ingestion source uses. This connector adds no
database write path of its own: tenancy scoping, identity isolation, and
upsert idempotency (Stage 8) apply completely unchanged.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy.engine import Engine

from backend.connectors.langfuse.client import LangfuseClient
from backend.connectors.langfuse.mapper import UnmappableTraceError, map_trace_to_session, resolve_version
from backend.connectors.langfuse.schemas import LangfuseImportPreview, LangfuseImportRequest, LangfuseImportResult
from backend.ingestion.schemas import IngestBatchRequest, IngestExperiment, IngestSession
from backend.ingestion.service import ingest_batch


class ExperimentMappingError(Exception):
    """Raised when no explicit experiment mapping was given and the
    fetched batch doesn't unambiguously imply one (anything other than
    exactly two distinct agent-version values). The connector never
    guesses which two versions are "control" and "treatment"."""


def _resolve_experiment(request: LangfuseImportRequest, traces: list[dict]) -> IngestExperiment:
    m = request.mapping
    if m.control_version and m.treatment_version and m.external_experiment_id and m.name:
        return IngestExperiment(
            external_experiment_id=m.external_experiment_id,
            name=m.name,
            control_version=m.control_version,
            treatment_version=m.treatment_version,
        )

    versions = Counter(resolve_version(t, m.version_field) for t in traces)
    if len(versions) != 2:
        raise ExperimentMappingError(
            f"No explicit experiment mapping was given, and {len(versions)} distinct agent version(s) "
            f"were found in this batch ({sorted(versions)}) — an experiment needs exactly two (control, "
            "treatment). Pass an explicit mapping (external_experiment_id, name, control_version, "
            "treatment_version) instead of relying on auto-detection."
        )
    (control, _), (treatment, _) = versions.most_common()
    external_experiment_id = m.external_experiment_id or f"langfuse-{request.start.date()}-{request.end.date()}"
    name = m.name or f"Langfuse import {request.start.date()} to {request.end.date()}"
    return IngestExperiment(
        external_experiment_id=external_experiment_id,
        name=name,
        control_version=m.control_version or control,
        treatment_version=m.treatment_version or treatment,
    )


def _fetch_and_map(client: LangfuseClient, request: LangfuseImportRequest) -> tuple[IngestExperiment, list[IngestSession], list[str], int]:
    summaries = list(client.fetch_traces(request.start, request.end, page_size=request.page_size))
    detailed = [client.fetch_trace_detail(t["id"]) for t in summaries]
    experiment = _resolve_experiment(request, detailed)

    sessions: list[IngestSession] = []
    skipped: list[str] = []
    for trace in detailed:
        try:
            sessions.append(
                map_trace_to_session(
                    trace,
                    external_experiment_id=experiment.external_experiment_id,
                    version_field=request.mapping.version_field,
                    outcome_metadata_key=request.mapping.outcome_metadata_key,
                )
            )
        except UnmappableTraceError as exc:
            skipped.append(str(exc))
    return experiment, sessions, skipped, len(detailed)


def preview_import(client: LangfuseClient, request: LangfuseImportRequest) -> LangfuseImportPreview:
    """Dry run (Stage 9 task 3): fetches from Langfuse and maps in
    memory, but never calls ingest_batch — guaranteed zero database
    writes, regardless of what the fetched batch contains."""
    experiment, sessions, skipped, traces_fetched = _fetch_and_map(client, request)
    return LangfuseImportPreview(
        domain=request.domain,
        traces_fetched=traces_fetched,
        sessions_mapped=len(sessions),
        sessions_skipped=len(skipped),
        skipped_reasons=skipped,
        derived_experiment=experiment,
        sample_sessions=sessions[:5],
    )


def run_import(engine: Engine, client: LangfuseClient, request: LangfuseImportRequest, project_id: str) -> LangfuseImportResult:
    """Actual import (Stage 9 task 3). Idempotent re-import is not a
    separate mode: calling this again with the same time range converges
    to the same stored state, since it goes through ingest_batch's own
    deterministic-id upsert (Stage 8) keyed by (project_id, domain,
    external_session_id) — the Langfuse trace/session id."""
    experiment, sessions, skipped, traces_fetched = _fetch_and_map(client, request)
    batch = IngestBatchRequest(domain=request.domain, experiments=[experiment], sessions=sessions)
    ingestion_response = ingest_batch(engine, batch, project_id=project_id)
    return LangfuseImportResult(
        domain=request.domain,
        traces_fetched=traces_fetched,
        sessions_skipped=len(skipped),
        skipped_reasons=skipped,
        ingestion=ingestion_response,
    )
