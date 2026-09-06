"""Stage 5: full validation pipeline at demo scale. Assumes the demo
dataset has already been generated (`python -m datagen.generate --profile
demo --seed 2024`) and loaded (`python -m datagen.load_to_postgres
--profile demo`), and that failure classification has been run
(`python -m scripts.run_classification --client mock`).

Ground truth (validation_ground_truth.parquet) is read ONLY at the very
end of this script, after every application-side computation is already
complete — never inside backend.investigation or backend.llm.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from backend.analytics import metric_registry
from backend.analytics.balance import assignment_integrity_checks, covariate_balance_report
from backend.analytics.data_quality import report_to_dataframe, run_full_report
from backend.analytics.experiment_results import analyze_all_metrics, analyze_metric, results_to_dataframe
from backend.analytics.sql_runner import run_sql_file
from backend.app.db import get_database_url
from backend.investigation.pipeline import run_investigation
from backend.investigation.segments import build_segment_registry
from backend.investigation.trajectory_attribution import _structural_features, reconstruct_trajectories
from backend.analytics.stats.clustering import cluster_arrays

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

DATA_DIR = Path("data")
PROFILE = "demo"
OUT_DIR = Path("reports/stage5")


def section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(get_database_url())
    timings: dict[str, float] = {}

    with engine.connect() as conn:
        row_counts = {
            t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            for t in ["users", "products", "experiments", "sessions", "messages", "agent_actions",
                      "tool_calls", "recommendations", "product_events", "evaluations", "failure_labels"]
        }
    section("0. Application row counts (demo, loaded)")
    for t, n in row_counts.items():
        print(f"  {t}: {n}")

    t0 = time.time()
    base_df = run_sql_file(engine, "session_level_base.sql")
    timings["base_query"] = time.time() - t0
    print(f"\nsession_level_base.sql: {len(base_df)} rows in {timings['base_query']:.2f}s")

    # --- Section 4: covariate balance ---
    section("4. Covariate balance (demo scale)")
    t0 = time.time()
    balance = covariate_balance_report(base_df)
    integrity = assignment_integrity_checks(base_df)
    timings["balance"] = time.time() - t0
    print(balance.to_string())
    print("\nAssignment integrity:", integrity)
    balance.to_csv(OUT_DIR / "covariate_balance.csv", index=False)

    # --- Section 5: full metric table ---
    section("5. Full v1-vs-v2 metric table (demo scale)")
    t0 = time.time()
    results = analyze_all_metrics(base_df, metric_registry.METRIC_REGISTRY)
    timings["full_metric_table"] = time.time() - t0
    metric_table = results_to_dataframe(results)
    print(metric_table.to_string())
    metric_table.to_csv(OUT_DIR / "metric_table.csv", index=False)
    print(f"\nfull metric table computed in {timings['full_metric_table']:.2f}s")

    # --- Section 3: data quality ---
    section("3. Data-quality / reconciliation report (demo scale)")
    t0 = time.time()
    dq_results = run_full_report(engine)
    dq_df = report_to_dataframe(dq_results)
    timings["data_quality"] = time.time() - t0
    print(dq_df.to_string())
    print(f"\nALL CHECKS PASSED: {dq_df.passed.all()}  ({len(dq_df)} checks) in {timings['data_quality']:.2f}s")
    dq_df.to_csv(OUT_DIR / "data_quality.csv", index=False)

    # --- Section 6/7: investigation, 3 lenses separately ---
    with engine.connect() as conn:
        actions = pd.read_sql(text("SELECT session_id, sequence_index, action_type::text AS action_type FROM agent_actions"), conn)
        labels = pd.read_sql(text("SELECT session_id, failure_mode::text AS failure_mode FROM failure_labels"), conn)

    investigations = {}
    for lens_name, metric_name in [("abandonment", "abandonment_rate"), ("conversion", "conversion_rate"), ("constraint_satisfaction", "constraint_satisfaction_rate")]:
        t0 = time.time()
        result = run_investigation(base_df, actions, labels, primary_metric_name=metric_name)
        timings[f"investigation_{lens_name}"] = time.time() - t0
        investigations[lens_name] = result

        section(f"6. Investigation lens={lens_name} (metric={metric_name}), demo scale")
        print(f"Overall: v1={result.overall.cluster_mean_v1:.4f} v2={result.overall.cluster_mean_v2:.4f} p={result.overall.p_value:.2e} verdict={result.overall.verdict}")
        print(f"Guardrails: {[(c.name, round(c.v1_value,5), round(c.v2_value,5), c.breached) for c in result.guardrails.checks]}")
        print(f"Explored, not significant: {result.explored_not_significant_count}")
        print(f"Recommendation: {result.recommendation.verdict} | reason: {result.recommendation.primary_reason}")
        print(f"  blocking: {result.recommendation.blocking_guardrails} | rules: {result.recommendation.rules_applied}")
        print(f"\n{len(result.findings)} top findings:")
        for f in result.findings:
            print(f"  [{f.segment_label}] v1={f.cluster_mean_v1:.4f} v2={f.cluster_mean_v2:.4f} p={f.p_value:.2e} effect_size={f.effect_size_value:.3f} EC={f.excess_contribution:.5f} dominant={f.dominant_failure_mode}")
            sig_traj = [a for a in f.trajectory_associations if a.bh_significant]
            for a in sig_traj:
                print(f"      TRAJECTORY (BH-sig): {a.pattern} n={a.n_sessions} rate={a.pattern_outcome_rate:.3f} vs base={a.baseline_outcome_rate:.3f} p={a.p_value:.2e}")
        print(f"(lens runtime: {timings[f'investigation_{lens_name}']:.2f}s)")

    # --- Section 9: trajectory reconstruction sanity ---
    section("9. Trajectory reconstruction (demo scale)")
    t0 = time.time()
    trajectories = reconstruct_trajectories(actions)
    timings["trajectory_reconstruction"] = time.time() - t0
    print(f"reconstructed {len(trajectories)} trajectories in {timings['trajectory_reconstruction']:.2f}s")
    print(f"distinct exact sequences: {trajectories.action_sequence.nunique()}")

    # --- Section 7: planted-effect recovery (ground truth read ONLY here) ---
    section("7. Planted-effect recovery (reading validation_ground_truth.parquet NOW, after all analysis above)")
    ground_truth = pd.read_parquet(DATA_DIR / PROFILE / "validation_ground_truth.parquet")
    ground_truth["session_id"] = ground_truth["session_id"].astype(str)

    def find_exact(result, label):
        return next((f for f in result.findings if f.segment_label == label), None)

    def rank_of(result, label):
        for i, f in enumerate(result.findings, start=1):
            if f.segment_label == label:
                return i
        return None

    # Stage 5 review correction: `dominant_failure_mode` is the Investigation
    # engine's CONVERSATIONAL failure-taxonomy attribution. It is a valid
    # mechanism descriptor only for effects whose planted mechanism actually
    # IS a conversational failure (overclarify_v2, monitor_constraint_regression_v2,
    # exploratory_uplift). android_latency's planted mechanism is a
    # non-conversational latency regression — the classifier has no "latency"
    # category, so its dominant_failure_mode for that segment is incidental
    # co-occurrence, not the cause. Reporting it as "mechanism" there would
    # let conversational attribution silently overwrite a known
    # non-conversational mechanism, so this table carries a mechanism_kind
    # tag and computes real latency evidence for the one non-conversational
    # effect instead of reusing dominant_failure_mode for it.
    checks = []

    f = find_exact(investigations["abandonment"], "constraint_count_bucket=3+")
    checks.append(("overclarify_v2", "constraint_count_bucket=3+", f is not None, f.cluster_mean_v2 > f.cluster_mean_v1 if f else None, rank_of(investigations["abandonment"], "constraint_count_bucket=3+"), "conversational", f.dominant_failure_mode if f else None))

    f = find_exact(investigations["abandonment"], "platform=android")
    android_mask = base_df["platform"] == "android"
    android_latency = base_df.loc[android_mask].groupby("agent_version")["total_latency_ms"].mean()
    latency_v1 = float(android_latency.get("v1", float("nan")))
    latency_v2 = float(android_latency.get("v2", float("nan")))
    p95_breach = next((g.breached for g in investigations["abandonment"].guardrails.checks if g.name == "p95_latency"), None)
    android_evidence = f"elevated Android latency: mean_total_latency_ms v1={latency_v1:.0f} v2={latency_v2:.0f} (+{(latency_v2 / latency_v1 - 1) * 100:.0f}%); p95_latency guardrail breached={p95_breach}"
    checks.append(("android_latency", "platform=android", f is not None, f.cluster_mean_v2 > f.cluster_mean_v1 if f else None, rank_of(investigations["abandonment"], "platform=android"), "non-conversational (latency)", android_evidence))

    f = find_exact(investigations["constraint_satisfaction"], "requested_category=monitor")
    checks.append(("monitor_constraint_regression_v2", "requested_category=monitor", f is not None, f.cluster_mean_v2 < f.cluster_mean_v1 if f else None, rank_of(investigations["constraint_satisfaction"], "requested_category=monitor"), "conversational", f.dominant_failure_mode if f else None))

    f = find_exact(investigations["constraint_satisfaction"], "constraint_count_bucket=0-1")
    checks.append(("exploratory_uplift", "constraint_count_bucket=0-1", f is not None, f.cluster_mean_v2 > f.cluster_mean_v1 if f else None, rank_of(investigations["constraint_satisfaction"], "constraint_count_bucket=0-1"), "conversational", f.dominant_failure_mode if f else None))

    # effect 5: independent re-derived check (not has_consecutive_search)
    trajectories["has_repeat_search_success"] = trajectories["action_sequence"].apply(
        lambda seq: _structural_features(seq)[1] >= 1 and not _structural_features(seq)[2]
    )
    merged = base_df.merge(trajectories, on="session_id")
    seg2 = merged[merged.constraint_count_bucket == "2"]
    arrays = cluster_arrays(seg2, "has_repeat_search_success")
    v1_rate = float(pd.Series(arrays.get("v1", [0])).mean())
    v2_rate = float(pd.Series(arrays.get("v2", [0])).mean())
    checks.append(("tool_selection_v2_improved", "constraint_count_bucket=2 (independent check)", True, v2_rate < v1_rate, None, "conversational", None))

    print(f"\n{'effect':38s} {'segment':45s} {'found':6s} {'v2 worse/better as expected':30s} {'rank':5s} {'mechanism_kind':28s} mechanism_evidence")
    for name, seg, found, direction_ok, rank, mechanism_kind, evidence in checks:
        print(f"{name:38s} {seg:45s} {str(found):6s} {str(direction_ok):30s} {str(rank):5s} {mechanism_kind:28s} {evidence}")
        assert (ground_truth.ground_truth_scenario == name).sum() > 0, f"{name} never fired in the demo dataset"

    # --- Section 8: false positives ---
    section("8. Unexplained (false-positive) findings check")
    scenario_by_session = ground_truth.set_index("session_id")["ground_truth_scenario"]
    for lens_name, result in investigations.items():
        for finding in result.findings:
            seg = next(s for s in build_segment_registry() if s.label == finding.segment_label)
            mask = seg.mask_fn(base_df)
            sids = base_df.loc[mask, "session_id"].astype(str)
            scenarios = scenario_by_session.reindex(sids).value_counts(normalize=True)
            dominant_scenario = scenarios.idxmax() if not scenarios.empty else "unknown"
            baseline_share = scenarios.get("baseline", 0)
            flag = "UNEXPLAINED" if baseline_share > 0.85 else ""
            print(f"  [{lens_name}] {finding.segment_label}: dominant_scenario={dominant_scenario} baseline_share={baseline_share:.2f} {flag}")

    section("13. Runtimes")
    for name, seconds in timings.items():
        print(f"  {name}: {seconds:.3f}s")

    print(f"\nReports written to {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
