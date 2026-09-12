"""AI Quality screen: the mandatory classifier evaluation report with
provenance.

Security fix: this router used to also serve GET
/experiments/{experiment_id}/ai-quality (failure-mode prevalence,
tool-use quality, trajectory patterns for one experiment), gated by
nothing more than get_current_user -- any authenticated user of any org
could read another org's AI-quality data by guessing/obtaining an
experiment id. That route is removed; the same data is now only
reachable through the project-scoped GET
/api/v1/domains/{domain}/experiments/{experiment_id}/ai-quality
(backend.app.routers.domains.get_domain_ai_quality), which verifies
project/org ownership via get_project_context. The route below,
classifier-evaluation, was never part of that bug: it reads only a
global, non-tenant classifier benchmark artifact, never a customer's
data, so it stays exactly as it was.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.schemas.ai_quality import (
    ClassifierAcceptanceBar,
    ClassifierEvaluationResponse,
    ClassifierPerClassMetric,
    DeterministicDetectorMetric,
    HybridEvaluationSummary,
    SemanticMechanismMetric,
)
from backend.app.schemas.common import ClassifierProvenance
from backend.llm.provenance import (
    CURRENT_HYBRID_EVALUATION_SUMMARY_PATH,
    DETERMINISTIC_DETECTORS_PERFECT_SCORE_NOTE,
    current_classifier_provenance_fields,
    get_evaluation_status,
    read_current_hybrid_evaluation_summary,
    read_evaluation_summary,
)

router = APIRouter(tags=["ai-quality"])


def _classifier_provenance() -> ClassifierProvenance:
    return ClassifierProvenance(evaluation_status=get_evaluation_status(), **current_classifier_provenance_fields())


def _hybrid_evaluation() -> HybridEvaluationSummary | None:
    """Stage 16: the current hybrid pipeline's own held-out benchmark
    (backend.llm.provenance.CURRENT_HYBRID_EVALUATION_SUMMARY_PATH), never
    recomputed here -- only reshaped into the API's schema."""
    raw = read_current_hybrid_evaluation_summary()
    if raw is None:
        return None
    det = raw["deterministic"]["per_mechanism"]
    sem = raw["semantic_metrics"]["per_mechanism"]
    evaluated_at = None
    if CURRENT_HYBRID_EVALUATION_SUMMARY_PATH.exists():
        evaluated_at = datetime.fromtimestamp(CURRENT_HYBRID_EVALUATION_SUMMARY_PATH.stat().st_mtime, tz=timezone.utc).isoformat()
    return HybridEvaluationSummary(
        subset=raw["subset"],
        provider="openrouter",
        model=raw["model"],
        prompt_version=raw["prompt_version"],
        detector_version=raw["detector_version"],
        evaluation_seed=raw["evaluation_seed"],
        subset_size=raw["subset_size"],
        deterministic_detectors=[
            DeterministicDetectorMetric(failure_mode=name, precision=m["precision"], recall=m["recall"], f1=m["f1"], support=m["support"])
            for name, m in det.items()
        ],
        deterministic_detectors_note=DETERMINISTIC_DETECTORS_PERFECT_SCORE_NOTE,
        semantic_metrics=[
            SemanticMechanismMetric(
                failure_mode=name, precision=m["precision"], recall=m["recall"], f1=m["f1"], support=m["support"],
                mean_confidence_correct=m.get("mean_confidence_correct"), mean_confidence_incorrect=m.get("mean_confidence_incorrect"),
            )
            for name, m in sem.items()
        ],
        semantic_micro_precision=raw["semantic_metrics"]["micro_precision"],
        semantic_micro_recall=raw["semantic_metrics"]["micro_recall"],
        semantic_micro_f1=raw["semantic_metrics"]["micro_f1"],
        semantic_macro_f1=raw["semantic_metrics"]["macro_f1"],
        semantic_exact_match_ratio=raw["semantic_metrics"]["exact_match_ratio"],
        semantic_hamming_loss=raw["semantic_metrics"]["hamming_loss"],
        semantic_coverage=raw["semantic_coverage"]["coverage"],
        evaluated_at=evaluated_at,
    )


@router.get("/ai-quality/classifier-evaluation", response_model=ClassifierEvaluationResponse)
def get_classifier_evaluation(user: CurrentUser = Depends(get_current_user)) -> ClassifierEvaluationResponse:
    """Mandatory offline evaluation report (AI_EVALUATION.md SS5). Reads
    only the pre-computed summary scripts/evaluate_classifier.py writes —
    this endpoint never touches validation_ground_truth.parquet itself."""
    provenance = _classifier_provenance()
    summary = read_evaluation_summary()

    if summary is None:
        return ClassifierEvaluationResponse(
            provenance=provenance, n_sessions_evaluated=None, overall_accuracy=None,
            mean_confidence_correct=None, mean_confidence_incorrect=None,
            per_class_metrics=[], acceptance_bars=[], all_acceptance_bars_met=None,
            hybrid_evaluation=_hybrid_evaluation(),
        )

    per_class = [
        ClassifierPerClassMetric(
            failure_mode=row["failure_mode"], support=row["support"],
            precision=row["precision"], recall=row["recall"], f1=row["f1"],
        )
        for row in summary.get("per_class_metrics", [])
    ]
    acceptance_bars = [
        ClassifierAcceptanceBar(
            failure_mode=row["failure_mode"], recall=row["recall"], recall_bar=row["recall_bar"],
            recall_pass=row["recall_pass"], precision=row["precision"], precision_bar=row["precision_bar"],
            precision_pass=row["precision_pass"],
        )
        for row in summary.get("acceptance_bars", [])
    ]
    return ClassifierEvaluationResponse(
        provenance=provenance,
        n_sessions_evaluated=summary.get("n_sessions_evaluated"),
        overall_accuracy=summary.get("overall_accuracy"),
        mean_confidence_correct=summary.get("mean_confidence_correct"),
        mean_confidence_incorrect=summary.get("mean_confidence_incorrect"),
        per_class_metrics=per_class,
        acceptance_bars=acceptance_bars,
        all_acceptance_bars_met=summary.get("acceptance_bars_met"),
        hybrid_evaluation=_hybrid_evaluation(),
    )
