"""Tests for the covariate-balance report and data-quality/reconciliation
checks (Stage 1 review requirements #4 and #6)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.analytics.balance import (
    SESSION_LEVEL_DIMENSIONS,
    USER_LEVEL_DIMENSIONS,
    assignment_integrity_checks,
    covariate_balance_report,
)
from backend.analytics.data_quality import run_full_report
from backend.analytics.sql_runner import run_sql_file


@pytest.fixture(scope="module")
def base_df(db_engine):
    return run_sql_file(db_engine, "session_level_base.sql")


def test_covariate_balance_report_covers_all_six_dimensions(base_df):
    report = covariate_balance_report(base_df)
    dims = set(report.dimension)
    assert dims == set(SESSION_LEVEL_DIMENSIONS) | set(USER_LEVEL_DIMENSIONS)


def test_covariate_balance_session_level_dimensions_are_descriptive_only(base_df):
    """Stage 2 review correction: session-varying covariates must not carry
    a session-level significance test (sessions are clustered within
    users) — only proportions and SMD, no chi-square/p-value."""
    report = covariate_balance_report(base_df)
    session_rows = report[report.unit == "session"]
    assert set(session_rows.dimension) == set(SESSION_LEVEL_DIMENSIONS)
    assert session_rows.p_value.isna().all(), "session-level covariates must not carry a p-value"
    assert session_rows.chi2_statistic.isna().all()
    assert (session_rows.method == "descriptive (proportions + SMD; no significance test - sessions are clustered within users)").all()


def test_covariate_balance_user_level_dimensions_use_chi_square(base_df):
    """persona/locale are fixed per user, so a chi-square at the user level
    is valid (each row is one independent user)."""
    report = covariate_balance_report(base_df)
    user_rows = report[report.unit == "user"]
    assert set(user_rows.dimension) == set(USER_LEVEL_DIMENSIONS)
    assert user_rows.p_value.notna().all()
    assert (user_rows.p_value >= 0.05).all(), "unexpectedly imbalanced fixed user attribute"


def test_covariate_balance_differences_are_small_in_absolute_terms(base_df):
    report = covariate_balance_report(base_df)
    assert (report.max_abs_pct_diff < 0.10).all(), "no pre-treatment dimension should differ by more than 10pp between arms"


def test_covariate_balance_session_level_dimensions_are_well_balanced_by_smd(base_df):
    """Conventional balance diagnostic: |SMD| < 0.1 (module docstring)."""
    report = covariate_balance_report(base_df)
    session_rows = report[report.unit == "session"]
    assert session_rows.well_balanced.all(), f"SMD >= 0.1 for: {session_rows[~session_rows.well_balanced].dimension.tolist()}"


def test_assignment_integrity_stable_and_no_dual_arm_users(base_df):
    checks = assignment_integrity_checks(base_df)
    assert checks["stable_assignment"] is True
    assert checks["users_in_both_arms"] == 0
    assert checks["balance_within_plausible_range"] is True


def test_data_quality_report_all_checks_pass(db_engine):
    results = run_full_report(db_engine)
    failed = [r for r in results if not r.passed]
    assert failed == [], f"data-quality checks failed: {[(r.name, r.violation_count) for r in failed]}"


def test_data_quality_report_has_at_least_20_checks(db_engine):
    """Coverage sanity: guards against someone accidentally gutting the
    check list rather than fixing a failing check."""
    results = run_full_report(db_engine)
    assert len(results) >= 20
