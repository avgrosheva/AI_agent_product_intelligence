"""Stage 3 task 6 / Stage 4 task 5 proof: using ONLY the generic core
(backend.analytics.experiment_results.analyze_metric, backend.core.
guardrails.evaluate_guardrails, backend.investigation.pipeline.
run_investigation) and the support domain's own adapter/registries —
never backend.app.models, never products/recommendations/product_events,
never backend.domains.commerce — show that:

  1. the ingested support-agent fixture can be read back as an
     analytics-ready session-level dataframe;
  2. its own north-star metric (resolution_rate) and other registered
     metrics can be compared v1 vs v2;
  3. its own guardrail can be evaluated;
  4. it has zero registered failure mechanisms, and nothing breaks;
  5. the FULL Investigation pipeline (segment scan over its own
     ticket_category dimension, BH correction, guardrail evaluation,
     deterministic ship/hold/roll_back recommendation) runs end to end,
     with no commerce entity involved anywhere.

Usage: python -m scripts.run_support_domain_demo
(requires the support fixture already ingested — see
scripts/generate_support_fixture.py + scripts/import_sessions.py)
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from backend.analytics.experiment_results import analyze_metric
from backend.app.db import get_database_url
from backend.core.guardrails import evaluate_guardrails
from backend.core.investigation_config import investigation_config_from_adapter
from backend.domains.support.adapter import SupportAdapter
from backend.investigation.pipeline import run_investigation


def main() -> None:
    engine = create_engine(get_database_url())
    adapter = SupportAdapter(engine)

    base_df = adapter.analytics_base_df()
    print(f"support domain analytics_base_df: {len(base_df)} sessions, "
          f"{int((base_df.agent_version == 'v1').sum())} v1 / {int((base_df.agent_version == 'v2').sum())} v2")
    print(f"columns: {sorted(base_df.columns)}")

    print("\n=== Metric comparison (generic analyze_metric, support's own metric_value_columns) ===")
    value_columns = adapter.metric_value_columns()
    for metric in adapter.metric_definitions():
        if metric.name not in value_columns:
            continue
        result = analyze_metric(base_df, metric, metric_value_columns=value_columns)
        print(
            f"  {metric.name:24s} v1={result.session_value_v1:.4f} v2={result.session_value_v2:.4f} "
            f"cluster_v1={result.cluster_mean_v1} cluster_v2={result.cluster_mean_v2} "
            f"p={result.p_value} verdict={result.verdict}"
        )

    print("\n=== Guardrails (generic evaluate_guardrails, support's own definitions) ===")
    report = evaluate_guardrails(base_df, adapter.guardrails())
    for check in report.checks:
        print(f"  {check.name}: v1={check.v1_value:.4f} v2={check.v2_value:.4f} ({check.threshold_description}) breached={check.breached}")
    print(f"  any_breach: {report.any_breach}")

    print("\n=== Mechanisms (Stage 3 task 7: no relevant detector configured) ===")
    mechanisms = adapter.mechanisms()
    print(f"  registered mechanisms: {mechanisms.all_names} (expected: empty tuple)")

    print("\n=== Sample detector-ready session context (generic core, no ProductEvidence) ===")
    sample_session_id = str(base_df.iloc[0]["session_id"])
    ctx = adapter.build_session_context(sample_session_id)
    print(f"  session_id={ctx.session_id} outcome={ctx.outcome!r} action_sequence={ctx.action_sequence} "
          f"tool_calls={[(t.tool_name, t.success) for t in ctx.tool_calls]}")

    print("\n=== Full Investigation pipeline (Stage 4 task 5): segment scan, BH correction, guardrails, recommendation ===")
    config = investigation_config_from_adapter(adapter)
    with engine.connect() as conn:
        actions_df = pd.read_sql(
            text(
                "SELECT session_id, sequence_index, action_type FROM ingested_actions "
                "WHERE session_id IN (SELECT session_id FROM ingested_sessions WHERE domain = :domain)"
            ),
            conn,
            params={"domain": adapter.domain},
        )
    actions_df["session_id"] = actions_df["session_id"].astype(str)
    # No failure-attribution storage exists for this domain (mechanisms()
    # is empty — Stage 3 task 7) — an empty wide-format frame with just the
    # join key is exactly what run_investigation expects in that case.
    failure_attributions_wide_df = pd.DataFrame(columns=["session_id"])

    result = run_investigation(base_df, actions_df, failure_attributions_wide_df, config, primary_metric_name="resolution_rate")
    print(f"  primary_metric={result.primary_metric} overall v1={result.overall.cluster_mean_v1:.4f} v2={result.overall.cluster_mean_v2:.4f} "
          f"p={result.overall.p_value} verdict={result.overall.verdict}")
    print(f"  segments scanned: {len(result.scan_rows)}, explored-not-significant: {result.explored_not_significant_count}")
    print(f"  top findings: {len(result.findings)}")
    for f in result.findings:
        print(f"    [{f.segment_label}] v1={f.cluster_mean_v1:.4f} v2={f.cluster_mean_v2:.4f} p={f.p_value:.2e} EC={f.excess_contribution:.4f} dominant_mode={f.dominant_failure_mode}")
    print(f"  guardrails any_breach={result.guardrails.any_breach}")
    print(f"  recommendation: verdict={result.recommendation.verdict}")
    print(f"    primary reason: {result.recommendation.primary_reason}")
    print(f"    next action: {result.recommendation.next_action}")
    print(f"    rules applied: {result.recommendation.rules_applied}")


if __name__ == "__main__":
    main()
