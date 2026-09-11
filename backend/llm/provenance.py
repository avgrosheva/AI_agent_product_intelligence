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

A third, independent file — real_llm_evaluation_summary.json, written by
scripts/run_real_llm_evaluation.py — holds the real-LLM subset evaluation
(provider, model, prompt version, seed, per-class metrics, cost, etc). It
is deliberately never the same file/path as the mock's evaluation summary:
the real-LLM run evaluates a few hundred sessions, not the full dataset,
and must never be presented as if it were the mock's (or vice versa) —
mock and real evaluation results are always distinguishable by which file
they came from.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

METADATA_PATH = Path("data/classifier_metadata.json")
EVALUATION_SUMMARY_PATH = Path("reports/stage3/classifier_evaluation_summary.json")
REAL_LLM_EVALUATION_SUMMARY_PATH = Path("reports/final/real_llm_evaluation_summary.json")

MOCK_CLASSIFIER_VERSION = "rule_based_mock-v1"

# Overall pipeline design version: distinguishes classifier_metadata.json
# snapshots written by the old exclusive-classifier pipeline (one
# FailureClassification per session, written to failure_labels) from the
# current hybrid multi-label pipeline (deterministic + semantic detectors,
# written to session_failure_attributions). A metadata record missing this
# field entirely is from before the redesign.
DETECTOR_ARCHITECTURE_VERSION = "hybrid_multi_label_v1"


def real_llm_classifier_version(provider: str, model: str) -> str:
    """classifier_version string for a real LLM client: "provider:model",
    e.g. "openrouter:anthropic/claude-sonnet-5". A single string keeps
    ClassifierMetadata's shape unchanged (no sidecar schema migration);
    parse_real_llm_version below recovers both fields for the API."""
    return f"{provider}:{model}"


def parse_real_llm_version(classifier_version: str) -> tuple[str, str] | None:
    """Inverse of real_llm_classifier_version. Returns (provider, model),
    or None if classifier_version isn't in "provider:model" form (e.g. the
    mock's plain "rule_based_mock-v1")."""
    if ":" not in classifier_version:
        return None
    provider, _, model = classifier_version.partition(":")
    return provider, model


@dataclass
class ClassifierMetadata:
    classifier_type: str    # "rule_based_mock" | "real_llm"
    classifier_version: str
    is_mock: bool
    run_at: str              # ISO timestamp
    n_sessions_classified: int
    # Added for the hybrid multi-label redesign; defaulted so a metadata
    # file written by the old pipeline still loads (as
    # detector_architecture_version=None, distinguishable from a current run).
    detector_architecture_version: str | None = None
    semantic_prompt_version: str | None = None


def write_classifier_metadata(
    classifier_type: str,
    classifier_version: str,
    is_mock: bool,
    n_sessions: int,
    detector_architecture_version: str | None = None,
    semantic_prompt_version: str | None = None,
) -> None:
    meta = ClassifierMetadata(
        classifier_type=classifier_type,
        classifier_version=classifier_version,
        is_mock=is_mock,
        run_at=datetime.now(timezone.utc).isoformat(),
        n_sessions_classified=n_sessions,
        detector_architecture_version=detector_architecture_version,
        semantic_prompt_version=semantic_prompt_version,
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


def write_real_llm_evaluation_summary(summary: dict) -> None:
    """Persists the real-LLM subset evaluation, independent of
    classifier_metadata.json and the mock's classifier_evaluation_summary.json
    (see module docstring). `summary` is expected to already contain
    provider/model/prompt_version/evaluation_seed/subset_size/metrics —
    this function only stamps evaluated_at and writes the file."""
    payload = {"evaluated_at": datetime.now(timezone.utc).isoformat(), **summary}
    REAL_LLM_EVALUATION_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REAL_LLM_EVALUATION_SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_real_llm_evaluation_summary() -> dict | None:
    if not REAL_LLM_EVALUATION_SUMMARY_PATH.exists():
        return None
    return json.loads(REAL_LLM_EVALUATION_SUMMARY_PATH.read_text(encoding="utf-8"))


# Stage 16: the CURRENT hybrid multi-label attribution pipeline's own
# held-out benchmark (scripts/run_hybrid_benchmark.py --subset
# new_holdout, AI_EVALUATION.md SS5) — a different file, a different
# shape, and a different (still-current) classifier architecture than
# REAL_LLM_EVALUATION_SUMMARY_PATH above, which is the DEPRECATED
# exclusive classifier's own real-LLM evaluation
# (scripts/run_real_llm_evaluation.py — see that script's own module
# docstring). Before this was wired in, nothing in the live API read the
# hybrid benchmark's result at all; the AI Quality screen's classifier-
# evaluation card only ever showed the deprecated shape/path (or "not
# evaluated yet" once that path was empty), regardless of a passing
# current-architecture evaluation sitting on disk.
CURRENT_HYBRID_EVALUATION_SUMMARY_PATH = Path("reports/final/semantic_holdout_200_summary.json")

# Explains, once, why a deterministic detector scoring 1.0 against this
# synthetic dataset's ground truth is expected, not a red flag: read
# AI_EVALUATION.md SS4 before assuming a passing score here says anything
# about behavior on real production data.
DETERMINISTIC_DETECTORS_PERFECT_SCORE_NOTE = (
    "retrieval_failure, poor_ranking, and wrong_tool_selection are pure functions of structured, already-observable "
    "fields (recommendations.satisfies_constraints, the action-type sequence) that this synthetic dataset's "
    "generator computed with the identical rule used to label ground truth for these three mechanisms "
    "(AI_EVALUATION.md SS4) -- a correctly-implemented detector is expected to match ground truth exactly here; "
    "this is not overfitting or a leaked signal. It validates that the detector correctly implements its "
    "documented rule against this dataset, not that it will score 1.0 against noisier real production telemetry."
)


def read_current_hybrid_evaluation_summary() -> dict | None:
    if not CURRENT_HYBRID_EVALUATION_SUMMARY_PATH.exists():
        return None
    return json.loads(CURRENT_HYBRID_EVALUATION_SUMMARY_PATH.read_text(encoding="utf-8"))


def current_classifier_provenance_fields() -> dict:
    """Shared by both routers that surface classifier provenance
    (sessions.py, ai_quality.py) so the classifier_type/provider/model
    parsing logic exists in exactly one place. Returns kwargs ready to
    pass into the ClassifierProvenance schema; callers still supply their
    own `evaluation_status` since that's endpoint-independent context."""
    meta = read_classifier_metadata()
    if meta is None:
        return {"classifier_type": "not_classified", "is_mock": False}
    provider, model = (None, None)
    if not meta.is_mock:
        parsed = parse_real_llm_version(meta.classifier_version)
        if parsed is not None:
            provider, model = parsed
    return {
        "classifier_type": meta.classifier_type,
        "classifier_version": meta.classifier_version,
        "provider": provider,
        "model": model,
        "is_mock": meta.is_mock,
        "run_at": meta.run_at,
    }


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
