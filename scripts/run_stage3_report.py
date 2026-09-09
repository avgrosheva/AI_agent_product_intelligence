"""Stage 3 deliverable report: runs the real Investigation pipeline
(observable data only) and prints/saves findings, failure attribution,
trajectory associations, guardrails, and the recommendation.

Usage: python -m scripts.run_stage3_report
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from backend.analytics.sql_runner import run_sql_file
from backend.app.db import get_database_url
from backend.domains.commerce.investigation_config import commerce_investigation_config
from backend.investigation.pipeline import run_investigation

_COMMERCE_CONFIG = commerce_investigation_config()

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

OUT_DIR = Path("reports/stage3")


def section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def print_investigation_result(result, label: str) -> None:
    section(f"Investigation run: primary_metric={result.primary_metric} ({label})")
    print(f"Overall: v1={result.overall.cluster_mean_v1:.4f} v2={result.overall.cluster_mean_v2:.4f} p={result.overall.p_value:.4f} verdict={result.overall.verdict}")
    print(f"Guardrails:")
    for c in result.guardrails.checks:
        print(f"  {c.name}: v1={c.v1_value:.4f} v2={c.v2_value:.4f} ({c.threshold_description}) breached={c.breached}")
    print(f"Segments explored, not significant: {result.explored_not_significant_count}")
    print(f"\nRecommendation: {result.recommendation.verdict}")
    print(f"  primary reason: {result.recommendation.primary_reason}")
    print(f"  blocking guardrails: {result.recommendation.blocking_guardrails}")
    print(f"  next action: {result.recommendation.next_action}")
    print(f"  rules applied: {result.recommendation.rules_applied}")

    print(f"\n--- {len(result.findings)} top findings ---")
    for f in result.findings:
        print(f"\n[{f.segment_label}] v1={f.cluster_mean_v1:.4f} v2={f.cluster_mean_v2:.4f} p={f.p_value:.2e} effect_size={f.effect_size_value} EC={f.excess_contribution:.4f}")
        fa = f.failure_attribution
        print(f"  excess_abandonment={fa.total_excess_abandonment:.2f} reportable={fa.reportable} dominant_mode={f.dominant_failure_mode}")
        for m in fa.per_mode:
            if m.share_of_excess_abandonment is not None and abs(m.share_of_excess_abandonment) > 0.01:
                print(f"    {m.failure_mode}: share_of_excess_abandonment={m.share_of_excess_abandonment:.3f} raw_share_of_v2_failures={m.raw_share_of_v2_failures}")
        sig_traj = [a for a in f.trajectory_associations if a.bh_significant]
        if sig_traj:
            for a in sig_traj:
                print(f"    TRAJECTORY (BH-significant): {a.pattern} n={a.n_sessions} rate={a.pattern_outcome_rate:.3f} vs baseline={a.baseline_outcome_rate:.3f} p={a.p_value:.4f}")
        else:
            best = min(f.trajectory_associations, key=lambda a: a.p_value, default=None)
            if best:
                print(f"    (no BH-significant trajectory pattern; closest: {best.pattern} p={best.p_value:.4f}, not significant after correction at dev scale)")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(get_database_url())
    timings = {}

    t0 = time.time()
    base_df = run_sql_file(engine, "session_level_base.sql")
    with engine.connect() as conn:
        actions = pd.read_sql(text("SELECT session_id, sequence_index, action_type::text AS action_type FROM agent_actions"), conn)
        labels = pd.read_sql(text("SELECT session_id, failure_mode::text AS failure_mode FROM failure_labels"), conn)
    timings["load_data"] = time.time() - t0

    t0 = time.time()
    result_abandonment = run_investigation(base_df, actions, labels, _COMMERCE_CONFIG, primary_metric_name="abandonment_rate")
    timings["investigation_abandonment_rate"] = time.time() - t0
    print_investigation_result(result_abandonment, "secondary lens, where the actual regression lives per Stage 2")

    t0 = time.time()
    result_conversion = run_investigation(base_df, actions, labels, _COMMERCE_CONFIG, primary_metric_name="conversion_rate")
    timings["investigation_conversion_rate"] = time.time() - t0
    print_investigation_result(result_conversion, "primary metric per INVESTIGATION.md default")

    t0 = time.time()
    result_satisfaction = run_investigation(base_df, actions, labels, _COMMERCE_CONFIG, primary_metric_name="constraint_satisfaction_rate")
    timings["investigation_constraint_satisfaction_rate"] = time.time() - t0
    print_investigation_result(result_satisfaction, "AI-quality lens, catches monitor/exploratory effects directionally")

    section("Runtimes")
    for name, seconds in timings.items():
        print(f"  {name}: {seconds:.3f}s")

    # Save a compact summary CSV of all findings across runs
    rows = []
    for label, result in [("abandonment_rate", result_abandonment), ("conversion_rate", result_conversion), ("constraint_satisfaction_rate", result_satisfaction)]:
        for f in result.findings:
            rows.append(
                {
                    "primary_metric": label, "segment": f.segment_label, "v1": f.cluster_mean_v1, "v2": f.cluster_mean_v2,
                    "p_value": f.p_value, "excess_contribution": f.excess_contribution, "dominant_failure_mode": f.dominant_failure_mode,
                }
            )
    pd.DataFrame(rows).to_csv(OUT_DIR / "findings_summary.csv", index=False)
    print(f"\nFindings summary written to {OUT_DIR / 'findings_summary.csv'}")


if __name__ == "__main__":
    main()
