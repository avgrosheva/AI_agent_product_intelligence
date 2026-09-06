"""Runs an LLMClient over every session and writes failure_labels
(source='llm_classifier' — the only value ever written to this table,
DATA_MODEL.md SS3.11). Idempotent: truncates and re-inserts on each run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from backend.app.models import FailureLabel
from backend.llm.anthropic_client import AnthropicLLMClient
from backend.llm.client import LLMClient
from backend.llm.context_builder import build_all_contexts
from backend.llm.mock_client import RuleBasedMockClient
from backend.llm.provenance import ANTHROPIC_CLASSIFIER_VERSION, MOCK_CLASSIFIER_VERSION, write_classifier_metadata

_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-4a5b-8c7d-9e0f1a2b3c4d")


def _describe_client(client: LLMClient) -> tuple[str, str, bool]:
    """(classifier_type, classifier_version, is_mock) for provenance
    tracking (Stage 3 review requirement #2) — not part of the LLMClient
    protocol itself, since only this pipeline needs it."""
    if isinstance(client, RuleBasedMockClient):
        return "rule_based_mock", MOCK_CLASSIFIER_VERSION, True
    if isinstance(client, AnthropicLLMClient):
        return "anthropic", ANTHROPIC_CLASSIFIER_VERSION, False
    return client.__class__.__name__, "unknown", False


def classify_all_sessions(engine: Engine, client: LLMClient) -> int:
    contexts = build_all_contexts(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    rows = []
    for ctx in contexts:
        classification = client.classify_failure(ctx)
        rows.append(
            {
                "label_id": uuid.uuid5(_NAMESPACE, f"label:{ctx.session_id}"),
                "session_id": ctx.session_id,
                "failure_mode": classification.failure_mode,
                "confidence": classification.confidence,
                "source": "llm_classifier",
                "evidence_text": classification.evidence_text,
                "created_at": now,
            }
        )

    with OrmSession(engine) as session:
        session.execute(delete(FailureLabel))
        if rows:
            session.execute(insert(FailureLabel), rows)
        session.commit()

    classifier_type, classifier_version, is_mock = _describe_client(client)
    write_classifier_metadata(classifier_type, classifier_version, is_mock, len(rows))

    return len(rows)
