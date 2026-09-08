"""Runs the hybrid multi-label attribution pipeline over every session and
writes session_failure_attributions (supersedes the old classify_all_sessions
/ FailureLabel path — backend.app.models.enums has the deprecation note).
One row per (session_id, failure_mode) for each of the six FailureMechanism
values, including detected=False rows, so "no mechanism fired" is always
derivable from the absence of a detected=True row, never itself a stored
prediction. Idempotent: truncates and re-inserts on each run.

Deterministic detectors (retrieval_failure, poor_ranking,
wrong_tool_selection) always run, for every session, regardless of which
LLMClient is configured — they are never guessed by an LLM, real or mock.
The one semantic call per session (unnecessary_clarification,
wrong_constraint_interpretation, unsupported_product_claim) uses whichever
LLMClient is passed in.

A session whose semantic call fails after retries (OpenRouterLLMClient's
classify_semantic raises) gets NO semantic rows written for that run — not
a disguised all-false result — so "not evaluated" and "evaluated as no
failure" stay distinguishable downstream.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.engine import Engine

from backend.app.models import SessionFailureAttribution
from backend.llm.client import LLMClient, MechanismResult, SessionContext
from backend.llm.context_builder import build_all_contexts
from backend.llm.deterministic_detectors import DETECTOR_VERSION, run_deterministic_detectors
from backend.llm.mock_client import RuleBasedMockClient
from backend.llm.openrouter_client import OpenRouterLLMClient
from backend.llm.provenance import (
    DETECTOR_ARCHITECTURE_VERSION,
    MOCK_CLASSIFIER_VERSION,
    real_llm_classifier_version,
    write_classifier_metadata,
)

# Distinct from the old FailureLabel pipeline's namespace (different last
# hex digit) so a deterministic id collision between the two schemas is
# structurally impossible, not just unlikely.
_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-4a5b-8c7d-9e0f1a2b3c4e")


def _describe_client(client: LLMClient) -> tuple[str, str, bool, str | None, str | None, str | None]:
    """(classifier_type, classifier_version, is_mock, provider, model, semantic_prompt_version)."""
    if isinstance(client, RuleBasedMockClient):
        return "rule_based_mock", MOCK_CLASSIFIER_VERSION, True, None, None, None
    if isinstance(client, OpenRouterLLMClient):
        return (
            "real_llm",
            real_llm_classifier_version("openrouter", client.model),
            False,
            "openrouter",
            client.model,
            client.semantic_prompt_version,
        )
    return client.__class__.__name__, "unknown", False, None, None, None


def _attribution_row(
    ctx: SessionContext,
    result: MechanismResult,
    detector_source: str,
    detector_version: str | None,
    provider: str | None,
    model: str | None,
    prompt_version: str | None,
    now,
) -> dict:
    return {
        "attribution_id": uuid.uuid5(_NAMESPACE, f"attr:{ctx.session_id}:{result.mechanism}"),
        "session_id": ctx.session_id,
        "failure_mode": result.mechanism,
        "detected": result.detected,
        "detector_source": detector_source,
        "confidence": result.confidence,
        "evidence_text": result.evidence_text,
        "detector_version": detector_version,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "created_at": now,
    }


_COPY_COLUMNS = (
    "attribution_id",
    "session_id",
    "failure_mode",
    "detected",
    "detector_source",
    "confidence",
    "evidence_text",
    "detector_version",
    "provider",
    "model",
    "prompt_version",
    "created_at",
)


def _bulk_write_attributions(engine: Engine, rows: list[dict]) -> None:
    """TRUNCATE + COPY FROM STDIN via the raw psycopg3 connection.

    Replaces a prior `session.execute(delete(...)); session.execute(insert
    (...), rows)` ORM path, which measured ~30 minutes for ~194k rows (one
    round trip per row under this driver/environment, even with
    SQLAlchemy's insertmanyvalues batching). COPY streams every row over a
    single wire operation. Same columns, same table, same enum/uniqueness
    constraints — Postgres COPY parses each value through the destination
    column's normal input function, so the two failure_mode/detector_source
    enum columns are validated exactly as they would be for a plain INSERT.
    TRUNCATE and COPY run in one transaction: either both land or neither
    does."""
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        cur.execute(f"TRUNCATE TABLE {SessionFailureAttribution.__tablename__}")
        if rows:
            copy_sql = f"COPY {SessionFailureAttribution.__tablename__} ({', '.join(_COPY_COLUMNS)}) FROM STDIN"
            with cur.copy(copy_sql) as copy:
                for row in rows:
                    copy.write_row(tuple(row[c] for c in _COPY_COLUMNS))
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def classify_all_sessions(engine: Engine, client: LLMClient) -> int:
    contexts = build_all_contexts(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    classifier_type, classifier_version, is_mock, provider, model, semantic_prompt_version = _describe_client(client)
    semantic_source = "mock_llm" if isinstance(client, RuleBasedMockClient) else "real_llm"

    rows: list[dict] = []
    n_semantic_failed = 0
    for ctx in contexts:
        for result in run_deterministic_detectors(ctx):
            rows.append(_attribution_row(ctx, result, "deterministic", DETECTOR_VERSION, None, None, None, now))

        try:
            semantic = client.classify_semantic(ctx)
        except Exception:
            # Malformed / retries exhausted: write no semantic rows for
            # this session this run, rather than a disguised all-false
            # prediction — see module docstring.
            n_semantic_failed += 1
            continue
        for result in semantic.results:
            rows.append(
                _attribution_row(ctx, result, semantic_source, classifier_version, provider, model, semantic_prompt_version, now)
            )

    _bulk_write_attributions(engine, rows)

    write_classifier_metadata(
        classifier_type,
        classifier_version,
        is_mock,
        len(contexts),
        detector_architecture_version=DETECTOR_ARCHITECTURE_VERSION,
        semantic_prompt_version=semantic_prompt_version,
    )

    return len(rows)
