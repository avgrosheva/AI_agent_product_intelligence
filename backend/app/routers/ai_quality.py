"""AI Quality screen: failure-mode distribution, tool-use quality,
trajectory pattern frequency (descriptive only — not an Investigation
finding), and the mandatory classifier evaluation report with provenance.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.dependencies import get_agent_actions_df, get_base_df, get_engine, get_experiment_or_404
from backend.app.schemas.ai_quality import (
    AIQualitySummaryResponse,
    ClassifierAcceptanceBar,
    ClassifierEvaluationResponse,
    ClassifierPerClassMetric,
    FailureMechanismPrevalenceItem,
    ToolUseQualitySchema,
    TrajectoryPatternFrequencyItem,
)
from backend.app.schemas.common import ClassifierProvenance
from backend.investigation.trajectory_attribution import canonicalize_patterns, reconstruct_trajectories
from backend.llm.client import DETERMINISTIC_MECHANISMS, FAILURE_MECHANISMS
from backend.llm.provenance import current_classifier_provenance_fields, get_evaluation_status, read_evaluation_summary

router = APIRouter(tags=["ai-quality"])


def _classifier_provenance() -> ClassifierProvenance:
    return ClassifierProvenance(evaluation_status=get_evaluation_status(), **current_classifier_provenance_fields())


@router.get("/experiments/{experiment_id}/ai-quality", response_model=AIQualitySummaryResponse)
def get_ai_quality_summary(experiment_id: str) -> AIQualitySummaryResponse:
    get_experiment_or_404(experiment_id)
    base_df = get_base_df(experiment_id=experiment_id)

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.agent_version::text AS agent_version, sfa.failure_mode::text AS failure_mode, count(*) AS n
                FROM session_failure_attributions sfa JOIN sessions s ON s.session_id = sfa.session_id
                WHERE s.experiment_id = :eid AND sfa.detected = true
                GROUP BY 1, 2
                """
            ),
            {"eid": experiment_id},
        ).mappings().all()
        source_rows = conn.execute(
            text("SELECT DISTINCT failure_mode::text AS failure_mode, detector_source::text AS detector_source FROM session_failure_attributions")
        ).mappings().all()
    counts: dict[str, dict[str, int]] = {}
    n_v1 = int((base_df.agent_version == "v1").sum())
    n_v2 = int((base_df.agent_version == "v2").sum())
    for r in rows:
        counts.setdefault(r["failure_mode"], {})[r["agent_version"]] = r["n"]
    sources = {r["failure_mode"]: r["detector_source"] for r in source_rows}

    # Prevalence, not an exclusive distribution: mechanisms can co-occur,
    # so rate_v1/rate_v2 summed across items do not sum to 1.0.
    prevalence = [
        FailureMechanismPrevalenceItem(
            failure_mode=mode,
            detector_source=sources.get(mode, "deterministic" if mode in DETERMINISTIC_MECHANISMS else "unknown"),
            count_v1=counts.get(mode, {}).get("v1", 0),
            count_v2=counts.get(mode, {}).get("v2", 0),
            rate_v1=(counts.get(mode, {}).get("v1", 0) / n_v1) if n_v1 else 0.0,
            rate_v2=(counts.get(mode, {}).get("v2", 0) / n_v2) if n_v2 else 0.0,
        )
        for mode in FAILURE_MECHANISMS
    ]

    tool_use = ToolUseQualitySchema(
        tool_calls_per_session_v1=float(base_df.loc[base_df.agent_version == "v1", "n_tool_calls"].mean()),
        tool_calls_per_session_v2=float(base_df.loc[base_df.agent_version == "v2", "n_tool_calls"].mean()),
        tool_success_rate_v1=float(base_df.loc[base_df.agent_version == "v1", "tool_success_rate_session"].mean()),
        tool_success_rate_v2=float(base_df.loc[base_df.agent_version == "v2", "tool_success_rate_session"].mean()),
        tool_error_rate_v1=float(base_df.loc[base_df.agent_version == "v1", "tool_error_rate_session"].mean()),
        tool_error_rate_v2=float(base_df.loc[base_df.agent_version == "v2", "tool_error_rate_session"].mean()),
    )

    actions_df = get_agent_actions_df()
    trajectories = reconstruct_trajectories(actions_df)
    merged = base_df.merge(trajectories, on="session_id", how="left")
    canon = canonicalize_patterns(merged.dropna(subset=["action_sequence"]))
    traj_items = []
    for pattern, group in canon.groupby("pattern"):
        v1 = group[group.agent_version == "v1"]
        v2 = group[group.agent_version == "v2"]
        if len(v1) + len(v2) < 5:
            continue
        traj_items.append(
            TrajectoryPatternFrequencyItem(
                pattern=pattern, n_sessions_v1=len(v1), n_sessions_v2=len(v2),
                abandonment_rate_v1=float(v1["abandoned"].mean()) if len(v1) else 0.0,
                abandonment_rate_v2=float(v2["abandoned"].mean()) if len(v2) else 0.0,
            )
        )
    traj_items.sort(key=lambda t: t.n_sessions_v1 + t.n_sessions_v2, reverse=True)

    return AIQualitySummaryResponse(
        experiment_id=experiment_id,
        failure_mechanism_prevalence=prevalence,
        tool_use_quality=tool_use,
        trajectory_patterns=traj_items,
        classifier_provenance=_classifier_provenance(),
    )


@router.get("/ai-quality/classifier-evaluation", response_model=ClassifierEvaluationResponse)
def get_classifier_evaluation() -> ClassifierEvaluationResponse:
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
    )
