"""Classifier provenance tracking (Stage 3 review requirement #2).

RuleBasedMockClient's accuracy must never be presented as real LLM
classifier performance. Every API response surfacing classifier output
must be able to say which implementation produced it, what version, and
whether it has been evaluated against ground truth — without adding a
ground-truth-adjacent column to the application schema (DATA_MODEL.md
SS3.11 keeps failure_labels.source as a single fixed value). This module
keeps that bookkeeping in a small JSON sidecar file instead.

Two files:
  - classifier_metadata.json: written by classification_pipeline.py every
    time failure_labels is (re)populated — which client, what version, when.
  - classifier_evaluation_summary.json: written by scripts/evaluate_classifier.py
    every time the mandatory offline evaluation (AI_EVALUATION.md SS5) runs —
    which classifier type was evaluated, when, with what results.

The API cross-references the two: if their classifier_type/version match,
the currently-loaded failure_labels have a corresponding evaluation on
record; if not (or the evaluation file is missing), that is surfaced
explicitly rather than silently reusing a stale or absent evaluation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

METADATA_PATH = Path("data/classifier_metadata.json")
EVALUATION_SUMMARY_PATH = Path("reports/stage3/classifier_evaluation_summary.json")

MOCK_CLASSIFIER_VERSION = "rule_based_mock-v1"
ANTHROPIC_CLASSIFIER_VERSION = "anthropic-claude-sonnet-5-v1"


@dataclass
class ClassifierMetadata:
    classifier_type: str    # "rule_based_mock" | "anthropic"
    classifier_version: str
    is_mock: bool
    run_at: str              # ISO timestamp
    n_sessions_classified: int


def write_classifier_metadata(classifier_type: str, classifier_version: str, is_mock: bool, n_sessions: int) -> None:
    meta = ClassifierMetadata(
        classifier_type=classifier_type,
        classifier_version=classifier_version,
        is_mock=is_mock,
        run_at=datetime.now(timezone.utc).isoformat(),
        n_sessions_classified=n_sessions,
    )
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def read_classifier_metadata() -> ClassifierMetadata | None:
    if not METADATA_PATH.exists():
        return None
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return ClassifierMetadata(**data)


def write_evaluation_summary(classifier_type: str, classifier_version: str, summary: dict) -> None:
    payload = {
        "evaluated_classifier_type": classifier_type,
        "evaluated_classifier_version": classifier_version,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        **summary,
    }
    EVALUATION_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVALUATION_SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_evaluation_summary() -> dict | None:
    if not EVALUATION_SUMMARY_PATH.exists():
        return None
    return json.loads(EVALUATION_SUMMARY_PATH.read_text(encoding="utf-8"))


def get_evaluation_status() -> str:
    """One of: 'evaluated_current' (matches the currently loaded
    failure_labels), 'evaluated_stale' (an evaluation exists but for a
    different classifier_type/version than what's currently loaded),
    'not_evaluated' (no evaluation on record), 'not_classified' (no
    failure_labels have been produced by any classifier yet)."""
    meta = read_classifier_metadata()
    if meta is None:
        return "not_classified"
    evaluation = read_evaluation_summary()
    if evaluation is None:
        return "not_evaluated"
    if (
        evaluation.get("evaluated_classifier_type") == meta.classifier_type
        and evaluation.get("evaluated_classifier_version") == meta.classifier_version
    ):
        return "evaluated_current"
    return "evaluated_stale"
