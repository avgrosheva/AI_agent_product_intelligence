"""Stage 3 task 6 proof: using ONLY the generic core (backend.analytics.
experiment_results.analyze_metric, backend.core.guardrails.evaluate_
guardrails) and the support domain's own adapter/registries — never
backend.app.models, never products/recommendations/product_events, never
backend.domains.commerce — show that:

  1. the ingested support-agent fixture can be read back as an
     analytics-ready session-level dataframe;
  2. its own north-star metric (resolution_rate) and other registered
     metrics can be compared v1 vs v2;
  3. its own guardrail can be evaluated;
  4. it has zero registered failure mechanisms, and nothing breaks.

Usage: python -m scripts.run_support_domain_demo
(requires the support fixture already ingested — see
scripts/generate_support_fixture.py + scripts/import_sessions.py)
"""

from __future__ import annotations

from sqlalchemy import create_engine

from backend.analytics.experiment_results import analyze_metric
from backend.app.db import get_database_url
from backend.core.guardrails import evaluate_guardrails
from backend.domains.support.adapter import SupportAdapter


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


if __name__ == "__main__":
    main()
