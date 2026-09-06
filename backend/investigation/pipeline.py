"""Investigation pipeline orchestration (INVESTIGATION.md SS3).

Operates only on observable application data passed in by the caller
(session-level base query + agent_actions + failure_labels) — never
validation_ground_truth.parquet, generation_manifest.json, Stage 2's
effect-verification helpers, or has_consecutive_search (Stage 2 review
requirement #4). tests/validate_ground_truth.py is the only place ground
truth is read, and only AFTER this pipeline has produced its output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.analytics import metric_registry
from backend.analytics.experiment_results import MetricResult, analyze_metric
from backend.analytics.stats.correction import benjamini_hochberg
from backend.investigation.failure_attribution import FailureAttributionResult, compute_failure_attribution
from backend.investigation.recommend import GuardrailReport, Recommendation, check_guardrails, synthesize_recommendation
from backend.investigation.scoring import (
    SegmentScanRow,
    apply_bh_correction,
    compute_excess_contribution,
    rank_findings,
    run_segment_scan,
)
from backend.investigation.thresholds import TOP_K_FINDINGS
from backend.investigation.trajectory_attribution import (
    PatternAssociation,
    canonicalize_patterns,
    reconstruct_trajectories,
    test_pattern_outcome_association,
)
from backend.llm.client import FAILURE_TAXONOMY


@dataclass
class Finding:
    segment_label: str
    dimensions: tuple[str, ...]
    n_users_v1: int
    n_users_v2: int
    cluster_mean_v1: float
    cluster_mean_v2: float
    p_value: float
    effect_size_value: float | None
    excess_contribution: float
    failure_attribution: FailureAttributionResult
    dominant_failure_mode: str | None
    trajectory_associations: list[PatternAssociation]


@dataclass
class InvestigationResult:
    primary_metric: str
    overall: MetricResult
    scan_rows: list[SegmentScanRow]
    findings: list[Finding]
    guardrails: GuardrailReport
    recommendation: Recommendation
    explored_not_significant_count: int


def _dominant_failure_mode(attribution: FailureAttributionResult) -> str | None:
    if not attribution.reportable:
        return None
    reportable_modes = [m for m in attribution.per_mode if m.failure_mode != "none" and m.share_of_excess_abandonment is not None]
    if not reportable_modes:
        return None
    return max(reportable_modes, key=lambda m: m.share_of_excess_abandonment).failure_mode


def run_investigation(
    base_df: pd.DataFrame,
    agent_actions_df: pd.DataFrame,
    failure_labels_df: pd.DataFrame,
    primary_metric_name: str = "conversion_rate",
    top_k: int = TOP_K_FINDINGS,
) -> InvestigationResult:
    metric_def = metric_registry.get(primary_metric_name)

    overall = analyze_metric(base_df, metric_def)

    scan_rows = run_segment_scan(base_df, primary_metric_name)
    scan_rows = apply_bh_correction(scan_rows)
    scan_rows = compute_excess_contribution(base_df, scan_rows, primary_metric_name, overall)
    top_rows = rank_findings(scan_rows, top_k=top_k)
    explored_not_significant = len(scan_rows) - len(top_rows)

    trajectories = reconstruct_trajectories(agent_actions_df)
    merged_with_labels = base_df.merge(failure_labels_df, on="session_id", how="left")
    merged_with_labels = merged_with_labels.merge(trajectories, on="session_id", how="left")

    all_trajectory_p_values: list[float] = []
    pending_associations: list[list[PatternAssociation]] = []

    findings: list[Finding] = []
    for row in top_rows:
        seg_mask = row.segment.mask_fn(merged_with_labels)
        seg_df = merged_with_labels[seg_mask]

        attribution = compute_failure_attribution(seg_df, FAILURE_TAXONOMY)
        attribution.segment_label = row.segment.label

        # Trajectory association: restricted to sessions that reached an
        # answer (outcome != 'abandoned') and tested against `converted` —
        # testing against `abandoned` itself would be tautological, since a
        # trajectory ending in abandon_flow determines that outcome by
        # construction, not as an independent downstream consequence.
        reached_answer = seg_df[seg_df["outcome"] != "abandoned"].dropna(subset=["action_sequence"])
        associations: list[PatternAssociation] = []
        if len(reached_answer) >= 10:
            canon = canonicalize_patterns(reached_answer)
            associations = test_pattern_outcome_association(canon, outcome_col="converted")
            pending_associations.append(associations)
            all_trajectory_p_values.extend(a.p_value for a in associations)

        findings.append(
            Finding(
                segment_label=row.segment.label,
                dimensions=row.segment.dimensions,
                n_users_v1=row.result.n_users_v1,
                n_users_v2=row.result.n_users_v2,
                cluster_mean_v1=row.result.cluster_mean_v1,
                cluster_mean_v2=row.result.cluster_mean_v2,
                p_value=row.result.p_value,
                effect_size_value=row.result.effect_size_value,
                excess_contribution=row.excess_contribution,
                failure_attribution=attribution,
                dominant_failure_mode=_dominant_failure_mode(attribution),
                trajectory_associations=associations,
            )
        )

    # Single BH pass across every trajectory-pattern test performed in this
    # run, pooled across all top segments (INVESTIGATION.md SS5: "again
    # BH-corrected within the run").
    if all_trajectory_p_values:
        rejected = benjamini_hochberg(all_trajectory_p_values, q=0.10)
        cursor = 0
        for associations in pending_associations:
            for assoc in associations:
                assoc.bh_significant = rejected[cursor]
                cursor += 1

    guardrails = check_guardrails(base_df)
    recommendation = synthesize_recommendation(overall, findings, guardrails)

    return InvestigationResult(
        primary_metric=primary_metric_name,
        overall=overall,
        scan_rows=scan_rows,
        findings=findings,
        guardrails=guardrails,
        recommendation=recommendation,
        explored_not_significant_count=explored_not_significant,
    )
