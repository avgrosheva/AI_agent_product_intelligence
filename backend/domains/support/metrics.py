"""The support domain's registered metrics — its own north-star metric,
outcome/funnel-equivalent metrics, and a quality signal, each bound to a
column `SupportAdapter.analytics_base_df()` produces. Nothing here is
commerce vocabulary: `resolution_rate` is this domain's north star, the
way `conversion_rate` is commerce's."""

from __future__ import annotations

from backend.core.metrics import MetricDefinition

SUPPORT_METRIC_REGISTRY: list[MetricDefinition] = [
    MetricDefinition(
        name="resolution_rate",
        semantic_class="outcome",
        source_tables=("ingested_sessions",),
        unit_of_measurement="proportion of sessions",
        unit_of_inference="user",
        numerator="count(sessions where outcome_label='resolved')",
        denominator="count(sessions)",
        eligibility_rule="all sessions in the experiment window",
        is_descriptive=True,
        is_inferential=True,
        cluster_stat_shape="symmetric",
        implemented=True,
        notes="Support domain's north-star metric — the equivalent role commerce's conversion_rate plays.",
        is_rate_metric=True,
    ),
    MetricDefinition(
        name="escalation_rate",
        semantic_class="outcome",
        source_tables=("ingested_sessions",),
        unit_of_measurement="proportion of sessions",
        unit_of_inference="user",
        numerator="count(sessions where outcome_label='escalated')",
        denominator="count(sessions)",
        eligibility_rule="all sessions",
        is_descriptive=True,
        is_inferential=True,
        cluster_stat_shape="symmetric",
        implemented=True,
        is_rate_metric=True,
    ),
    MetricDefinition(
        name="csat_score",
        semantic_class="outcome",
        source_tables=("ingested_metrics",),
        unit_of_measurement="1-5 rating",
        unit_of_inference="user",
        numerator="mean(ingested_metrics.value where name='csat_score')",
        denominator="n/a (continuous mean)",
        eligibility_rule="sessions with a csat_score metric present",
        is_descriptive=True,
        is_inferential=True,
        cluster_stat_shape="symmetric",
        implemented=True,
        is_rate_metric=False,
    ),
    MetricDefinition(
        name="handle_time_seconds",
        semantic_class="post_treatment_mechanism",
        source_tables=("ingested_metrics",),
        unit_of_measurement="seconds",
        unit_of_inference="user",
        numerator="mean(ingested_metrics.value where name='handle_time_seconds')",
        denominator="n/a (continuous mean)",
        eligibility_rule="sessions with a handle_time_seconds metric present",
        is_descriptive=True,
        is_inferential=True,
        cluster_stat_shape="symmetric",
        implemented=True,
        is_rate_metric=False,
    ),
]

# metric_name -> (value_column, eligibility_mask_fn | None) — same shape
# backend.analytics.experiment_results.analyze_metric already expects.
SUPPORT_METRIC_VALUE_COLUMNS: dict[str, tuple[str, object]] = {
    "resolution_rate": ("resolved", None),
    "escalation_rate": ("escalated", None),
    "csat_score": ("csat_score", lambda df: df.csat_score.notna()),
    "handle_time_seconds": ("handle_time_seconds", lambda df: df.handle_time_seconds.notna()),
}
