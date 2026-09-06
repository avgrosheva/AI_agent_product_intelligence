"""Stage 2 deliverable report: runs every analysis in backend/analytics
against the loaded dev dataset and prints/saves the full set of outputs
required by the Stage 2 review (metric table, funnel, covariate balance,
data quality, 5 planted-effect verifications, SQL analyses).

Usage: python -m scripts.run_stage2_report
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from backend.analytics import metric_registry
from backend.analytics.balance import assignment_integrity_checks, covariate_balance_report
from backend.analytics.data_quality import report_to_dataframe, run_full_report
from backend.analytics.effects_verification import (
    verify_android_latency_effect,
    verify_named_effects,
    verify_tool_selection_effect,
)
from backend.analytics.experiment_results import analyze_all_metrics, results_to_dataframe
from backend.analytics.sql_runner import list_sql_files, run_sql_file
from backend.app.db import get_database_url

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_rows", 100)

OUT_DIR = Path("reports/stage2")


def section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(get_database_url())
    timings = {}

    t0 = time.time()
    base_df = run_sql_file(engine, "session_level_base.sql")
    timings["session_level_base_query"] = time.time() - t0

    section("1. Full v1-vs-v2 metric table (user-level cluster inference)")
    t0 = time.time()
    results = analyze_all_metrics(base_df, metric_registry.METRIC_REGISTRY)
    metric_table = results_to_dataframe(results)
    timings["experiment_results_all_metrics"] = time.time() - t0
    print(metric_table.to_string())
    metric_table.to_csv(OUT_DIR / "metric_table.csv", index=False)

    section("2. Funnel comparison (descriptive SQL)")
    funnel = run_sql_file(engine, "02_funnel_by_version.sql")
    print(funnel.to_string())
    funnel.to_csv(OUT_DIR / "funnel.csv", index=False)

    section("3. Covariate balance report")
    t0 = time.time()
    balance = covariate_balance_report(base_df)
    integrity = assignment_integrity_checks(base_df)
    timings["covariate_balance"] = time.time() - t0
    print(balance.to_string())
    print("\nAssignment integrity:", integrity)
    balance.to_csv(OUT_DIR / "covariate_balance.csv", index=False)

    section("4. Data-quality / reconciliation report")
    t0 = time.time()
    dq_results = run_full_report(engine)
    dq_df = report_to_dataframe(dq_results)
    timings["data_quality_report"] = time.time() - t0
    print(dq_df.to_string())
    print(f"\nALL CHECKS PASSED: {dq_df.passed.all()}  ({len(dq_df)} checks)")
    dq_df.to_csv(OUT_DIR / "data_quality.csv", index=False)

    section("5. Manual verification of the five planted effects (observable data only)")
    t0 = time.time()
    effects_report = verify_named_effects(base_df)
    tool_selection = verify_tool_selection_effect(base_df)
    android = verify_android_latency_effect(base_df)
    timings["effects_verification"] = time.time() - t0
    print(effects_report.to_string())
    print("\nTool-selection effect:", tool_selection)
    print("\nAndroid-latency effect:", android)
    effects_report.to_csv(OUT_DIR / "effects_verification.csv", index=False)

    section("6. Representative SQL analyses (8 files)")
    for filename in list_sql_files():
        print(f"\n--- {filename} ---")
        df = run_sql_file(engine, filename)
        print(df.head(15).to_string())

    section("7. Runtimes")
    for name, seconds in timings.items():
        print(f"  {name}: {seconds:.3f}s")

    print(f"\nCSV outputs written to {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
