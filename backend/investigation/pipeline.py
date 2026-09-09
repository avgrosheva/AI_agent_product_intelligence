"""Investigation pipeline orchestration (INVESTIGATION.md SS3).

Operates only on observable application data passed in by the caller
(session-level base query + agent_actions + session_failure_attributions,
wide-format) — never
validation_ground_truth.parquet, generation_manifest.json, Stage 2's
effect-verification helpers, or has_consecutive_search (Stage 2 review
requirement #4). tests/validate_ground_truth.py is the only place ground
truth is read, and only AFTER this pipeline has produced its output.

Stage 4: this module holds no commerce (or any other domain) default.
Every domain-specific input — metric registry/value-columns, segment
dimensions/allowlist, guardrails, registered mechanisms, next-action
templates — comes from the required `config: InvestigationConfig`
argument, built from the active DomainAdapter
(backend.core.investigation_config.investigation_config_from_adapter). A
domain with an empty MechanismRegistry (config.mechanisms == ()) simply
gets no failure-attribution decomposition or trajectory-association
analysis per finding — those explain WHY a registered mechanism fired,
which does not apply when no mechanism is registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.analytics.experiment_results import MetricResult, analyze_metric
from backend.analytics.stats.correction import benjamini_hochberg
from backend.core.guardrails import evaluate_guardrails
from backend.core.investigation_config import InvestigationConfig
from backend.core.metrics import get_metric
from backend.investigation.failure_attribution import FailureAttributionResult, compute_failure_attribution
from backend.investigation.recommend import GuardrailReport, Recommendation, synthesize_recommendation
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
    reportable_modes = [m for m in attribution.per_mode if m.share_of_excess_abandonment is not None]
    if not reportable_modes:
        return None
    return max(reportable_modes, key=lambda m: m.share_of_excess_abandonment).failure_mode


def run_investigation(
    base_df: pd.DataFrame,
    agent_actions_df: pd.DataFrame,
    failure_attributions_wide_df: pd.DataFrame,
    config: InvestigationConfig,
    primary_metric_name: str = "conversion_rate",
    top_k: int = TOP_K_FINDINGS,
) -> InvestigationResult:
    metric_def = get_metric(primary_metric_name, config.metric_registry)

    overall = analyze_metric(base_df, metric_def, metric_value_columns=config.metric_value_columns)

    scan_rows = run_segment_scan(base_df, primary_metric_name, config)
    scan_rows = apply_bh_correction(scan_rows)
    scan_rows = compute_excess_contribution(base_df, scan_rows, primary_metric_name, overall, config)
    top_rows = rank_findings(scan_rows, top_k=top_k)
    explored_not_significant = len(scan_rows) - len(top_rows)

    trajectories = reconstruct_trajectories(agent_actions_df)
    merged_with_labels = base_df.merge(failure_attributions_wide_df, on="session_id", how="left")
    # NaN means "no attribution row for this session" (never classified, or
    # a semantic call failed and wrote nothing that run) — treated as
    # not-detected for this aggregate decomposition, same simplification
    # the old exclusive labeling made implicitly by defaulting to "none".
    # config.mechanisms may be () for a domain with no registered detector
    # (Stage 4 task 7) — assigning to zero columns here is a no-op.
    merged_with_labels[list(config.mechanisms)] = merged_with_labels[list(config.mechanisms)].fillna(False)
    merged_with_labels = merged_with_labels.merge(trajectories, on="session_id", how="left")

    all_trajectory_p_values: list[float] = []
    pending_associations: list[list[PatternAssociation]] = []

    findings: list[Finding] = []
    for row in top_rows:
        seg_mask = row.segment.mask_fn(merged_with_labels)
        seg_df = merged_with_labels[seg_mask]

        associations: list[PatternAssociation] = []
        if config.mechanisms:
            # Failure-mode decomposition and trajectory-pattern association
            # both explain WHY a registered mechanism fired — meaningless
            # (and, for the trajectory_config's outcome/action columns, not
            # even guaranteed to exist) for a domain that registers none.
            attribution = compute_failure_attribution(seg_df, config.mechanisms)
            attribution.segment_label = row.segment.label

            # Trajectory association: restricted to sessions that reached an
            # answer (outcome != trajectory_config.negative_outcome_value)
            # and tested against trajectory_config.positive_outcome_column —
            # testing against the negative outcome itself would be
            # tautological, since a trajectory ending in
            # terminal_negative_action determines that outcome by
            # construction, not as an independent downstream consequence
            # (Stage 5 task 5: these were commerce-hardcoded literals —
            # "outcome"/"abandoned"/"converted" — now sourced from the
            # active domain's own TrajectoryConfig).
            tc = config.trajectory_config
            reached_answer = seg_df[seg_df[tc.outcome_column] != tc.negative_outcome_value].dropna(subset=["action_sequence"])
            if len(reached_answer) >= 10:
                canon = canonicalize_patterns(
                    reached_answer,
                    clarify_action=tc.clarify_action,
                    repeat_action=tc.repeat_action,
                    terminal_negative_action=tc.terminal_negative_action,
                )
                associations = test_pattern_outcome_association(canon, outcome_col=tc.positive_outcome_column)
                pending_associations.append(associations)
                all_trajectory_p_values.extend(a.p_value for a in associations)
        else:
            attribution = FailureAttributionResult(
                segment_label=row.segment.label,
                n_v1=row.result.n_users_v1,
                n_v2=row.result.n_users_v2,
                abandonment_rate_v1=0.0,
                abandonment_rate_v2=0.0,
                total_excess_abandonment=0.0,
                per_mode=[],
                reportable=False,
            )

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

    guardrails = evaluate_guardrails(base_df, config.guardrails)
    recommendation = synthesize_recommendation(overall, findings, guardrails, next_action_templates=config.next_action_templates)

    return InvestigationResult(
        primary_metric=primary_metric_name,
        overall=overall,
        scan_rows=scan_rows,
        findings=findings,
        guardrails=guardrails,
        recommendation=recommendation,
        explored_not_significant_count=explored_not_significant,
    )
