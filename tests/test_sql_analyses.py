"""Smoke tests for the 8 representative SQL analyses plus the shared
session-level base query (Stage 1 review requirement: SQL must stay
visible and readable, not hidden behind pandas/ORM abstractions)."""

from __future__ import annotations

from backend.analytics.sql_runner import list_sql_files, run_sql_file


def test_eight_representative_analyses_are_present():
    files = list_sql_files()
    numbered = [f for f in files if f[0].isdigit()]
    assert len(numbered) == 8


def test_every_sql_file_executes_and_returns_both_arms(db_engine):
    for filename in list_sql_files():
        df = run_sql_file(db_engine, filename)
        assert not df.empty, f"{filename} returned no rows"
        if "agent_version" in df.columns:
            assert set(df["agent_version"].unique()) >= {"v1", "v2"}, f"{filename} is missing an arm"


def test_funnel_rates_are_monotonically_decreasing(db_engine):
    df = run_sql_file(db_engine, "02_funnel_by_version.sql")
    for _, row in df.iterrows():
        assert row.n_impression >= row.n_click >= row.n_cart >= row.n_purchase


def test_covariate_balance_percentages_sum_to_one_per_dimension_and_arm(db_engine):
    df = run_sql_file(db_engine, "07_covariate_balance.sql")
    totals = df.groupby(["dimension", "agent_version"])["pct_within_arm"].sum()
    assert (totals.round(6) == 1.0).all()
