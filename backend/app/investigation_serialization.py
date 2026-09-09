"""Shared Investigation-result -> API-schema mapping (Stage 3's commerce
/investigation endpoint and Stage 5's generic /domains/{domain}/.../
investigation endpoint both call this — it operates on the generic
backend.investigation.pipeline.Finding/InvestigationResult shapes, no
domain-specific data of its own).
"""

from __future__ import annotations

from backend.app.schemas.investigation import (
    FailureAttributionSchema,
    FailureModeShare,
    FindingSchema,
    SegmentFilter,
    TrajectoryAssociationSchema,
)


def values_from_label(segment_label: str) -> list[str]:
    """'constraint_count_bucket=3+ & platform=android' -> ['3+', 'android']."""
    parts = segment_label.split(" & ")
    return [p.split("=", 1)[1] for p in parts]


def finding_to_schema(finding) -> FindingSchema:
    fa = finding.failure_attribution
    return FindingSchema(
        segment_label=finding.segment_label,
        segment_filter=SegmentFilter(dimensions=dict(zip(finding.dimensions, values_from_label(finding.segment_label)))),
        n_users_v1=finding.n_users_v1,
        n_users_v2=finding.n_users_v2,
        cluster_mean_v1=finding.cluster_mean_v1,
        cluster_mean_v2=finding.cluster_mean_v2,
        p_value=finding.p_value,
        effect_size_value=finding.effect_size_value,
        excess_contribution=finding.excess_contribution,
        dominant_failure_mode=finding.dominant_failure_mode,
        failure_attribution=FailureAttributionSchema(
            n_v1=fa.n_v1, n_v2=fa.n_v2,
            abandonment_rate_v1=fa.abandonment_rate_v1, abandonment_rate_v2=fa.abandonment_rate_v2,
            total_excess_abandonment=fa.total_excess_abandonment, reportable=fa.reportable,
            per_mode=[
                FailureModeShare(
                    failure_mode=m.failure_mode, excess_count=m.excess_count,
                    share_of_excess_abandonment=m.share_of_excess_abandonment,
                    raw_share_of_v2_failures=m.raw_share_of_v2_failures,
                )
                for m in fa.per_mode
            ],
        ),
        trajectory_associations=[
            TrajectoryAssociationSchema(
                pattern=a.pattern, n_sessions=a.n_sessions, pattern_outcome_rate=a.pattern_outcome_rate,
                baseline_outcome_rate=a.baseline_outcome_rate, test_name=a.test_name, p_value=a.p_value,
                bh_significant=a.bh_significant,
            )
            for a in finding.trajectory_associations
        ],
    )
