"""Stage 10 tasks 3/6/9: pure coercion and duplicate-resolution tests for
backend.connectors.postgres_business.mapper — no database, no HTTP."""

from __future__ import annotations

import pytest

from backend.connectors.postgres_business.mapper import TypeMismatchError, coerce_value, dedupe_rows
from backend.connectors.postgres_business.schemas import PostgresJoinConfig, PostgresMetricMapping, PostgresSourceConfig


def _source(timestamp_column: str | None = None) -> PostgresSourceConfig:
    return PostgresSourceConfig(
        table="business_data",
        join=PostgresJoinConfig(join_key_column="external_session_id", timestamp_column=timestamp_column),
        metrics=[
            PostgresMetricMapping(source_column="revenue_usd", metric_name="revenue_usd", value_type="numeric"),
            PostgresMetricMapping(source_column="order_completed", metric_name="order_completed", value_type="boolean"),
        ],
    )


# -- coerce_value -----------------------------------------------------


def test_coerce_null_passes_through_as_none():
    assert coerce_value(None, "numeric") is None
    assert coerce_value(None, "boolean") is None


def test_coerce_numeric_from_int_float_and_string():
    assert coerce_value(5, "numeric") == 5.0
    assert coerce_value(5.5, "numeric") == 5.5
    assert coerce_value("12.3", "numeric") == 12.3


def test_coerce_numeric_rejects_non_numeric_string():
    with pytest.raises(TypeMismatchError):
        coerce_value("not-a-number", "numeric")


def test_coerce_numeric_rejects_bool():
    # bool is an int subclass in Python -- must not silently pass as 0.0/1.0
    with pytest.raises(TypeMismatchError):
        coerce_value(True, "numeric")


def test_coerce_boolean_from_bool_int_and_string():
    assert coerce_value(True, "boolean") == 1.0
    assert coerce_value(False, "boolean") == 0.0
    assert coerce_value(1, "boolean") == 1.0
    assert coerce_value(0, "boolean") == 0.0
    assert coerce_value("true", "boolean") == 1.0
    assert coerce_value("No", "boolean") == 0.0


def test_coerce_boolean_rejects_unrecognized_string():
    with pytest.raises(TypeMismatchError):
        coerce_value("maybe", "boolean")


def test_coerce_boolean_rejects_out_of_range_number():
    with pytest.raises(TypeMismatchError):
        coerce_value(2, "boolean")


# -- dedupe_rows --------------------------------------------------------


def test_single_row_per_key_passes_through_unchanged():
    rows = [{"external_session_id": "s1", "revenue_usd": 10.0, "order_completed": True}]
    resolved, issues = dedupe_rows(rows, _source())
    assert resolved == rows
    assert issues == []


def test_exact_duplicate_rows_collapse_silently():
    row = {"external_session_id": "s1", "revenue_usd": 10.0, "order_completed": True}
    resolved, issues = dedupe_rows([row, dict(row)], _source())
    assert len(resolved) == 1
    assert issues == []


def test_conflicting_duplicates_without_timestamp_are_reported_not_guessed():
    rows = [
        {"external_session_id": "s1", "revenue_usd": 10.0, "order_completed": True},
        {"external_session_id": "s1", "revenue_usd": 99.0, "order_completed": False},
    ]
    resolved, issues = dedupe_rows(rows, _source())
    assert resolved == []  # neither conflicting row is used
    assert len(issues) == 1
    assert "s1" in issues[0].message


def test_conflicting_duplicates_resolved_by_most_recent_timestamp():
    rows = [
        {"external_session_id": "s1", "revenue_usd": 10.0, "order_completed": True, "recorded_at": "2026-01-01T00:00:00"},
        {"external_session_id": "s1", "revenue_usd": 99.0, "order_completed": False, "recorded_at": "2026-06-01T00:00:00"},
    ]
    resolved, issues = dedupe_rows(rows, _source(timestamp_column="recorded_at"))
    assert len(resolved) == 1
    assert resolved[0]["revenue_usd"] == 99.0
    assert issues == []


def test_different_keys_are_independent():
    rows = [
        {"external_session_id": "s1", "revenue_usd": 10.0, "order_completed": True},
        {"external_session_id": "s2", "revenue_usd": 20.0, "order_completed": True},
    ]
    resolved, issues = dedupe_rows(rows, _source())
    assert len(resolved) == 2
    assert issues == []
