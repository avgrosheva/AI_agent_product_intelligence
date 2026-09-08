"""Referential integrity, schema constraints, and enum validity against the
loaded Postgres database (DATA_MODEL.md SS3, SS9)."""

from __future__ import annotations

import pytest
from sqlalchemy import text


def _scalar(engine, sql: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def test_all_expected_tables_exist(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        ).fetchall()
    tables = {r[0] for r in rows}
    expected = {
        "users", "products", "experiments", "sessions", "messages", "agent_actions",
        "tool_calls", "recommendations", "product_events", "evaluations", "failure_labels",
        "session_failure_attributions",
    }
    assert expected.issubset(tables)


def test_no_orphan_sessions(db_engine):
    assert _scalar(db_engine, "SELECT count(*) FROM sessions s LEFT JOIN users u ON s.user_id=u.user_id WHERE u.user_id IS NULL") == 0
    assert _scalar(db_engine, "SELECT count(*) FROM sessions s LEFT JOIN experiments e ON s.experiment_id=e.experiment_id WHERE e.experiment_id IS NULL") == 0


def test_no_orphan_child_rows(db_engine):
    checks = [
        ("messages", "session_id", "sessions", "session_id"),
        ("agent_actions", "session_id", "sessions", "session_id"),
        ("tool_calls", "session_id", "sessions", "session_id"),
        ("tool_calls", "action_id", "agent_actions", "action_id"),
        ("recommendations", "session_id", "sessions", "session_id"),
        ("recommendations", "product_id", "products", "product_id"),
        ("product_events", "session_id", "sessions", "session_id"),
        ("product_events", "user_id", "users", "user_id"),
        ("product_events", "product_id", "products", "product_id"),
        ("evaluations", "session_id", "sessions", "session_id"),
    ]
    for child_table, child_col, parent_table, parent_col in checks:
        sql = (
            f"SELECT count(*) FROM {child_table} c "
            f"LEFT JOIN {parent_table} p ON c.{child_col}=p.{parent_col} "
            f"WHERE p.{parent_col} IS NULL"
        )
        assert _scalar(db_engine, sql) == 0, f"orphan rows found: {child_table}.{child_col} -> {parent_table}.{parent_col}"


def test_row_counts_are_nonzero_where_expected(db_engine):
    for table in ["users", "products", "experiments", "sessions", "messages", "agent_actions", "tool_calls", "recommendations", "product_events", "evaluations"]:
        assert _scalar(db_engine, f"SELECT count(*) FROM {table}") > 0, f"{table} is unexpectedly empty"


@pytest.mark.order(1)
def test_failure_labels_is_empty_in_stage_1(db_engine):
    """failure_labels is the old exclusive-classifier table, deprecated by
    the hybrid multi-label redesign (backend.app.models.enums) — nothing
    writes to it anymore, so unlike session_failure_attributions below this
    stays empty permanently, not just in Stage 1.

    Pinned to run first (pytest-order) rather than relying on alphabetical
    file-collection order: db_engine's truncate-and-reload is session-scoped
    (runs once), and later tests/validate_ground_truth.py's classified_engine
    fixture populates session_failure_attributions on top of that same
    session — this assertion is only meaningful if it observes the DB
    before that happens.
    """
    assert _scalar(db_engine, "SELECT count(*) FROM failure_labels") == 0


@pytest.mark.order(1)
def test_session_failure_attributions_is_empty_in_stage_1(db_engine):
    """Stage 1 leaves session_failure_attributions empty: classification is
    Stage 3 (AI_EVALUATION.md, ROADMAP.md Stage 3). Same ordering rationale
    as test_failure_labels_is_empty_in_stage_1 above."""
    assert _scalar(db_engine, "SELECT count(*) FROM session_failure_attributions") == 0


def test_enum_columns_only_contain_documented_values(db_engine):
    checks = {
        "sessions": {
            "agent_version": {"v1", "v2"},
            "platform": {"web", "ios", "android"},
            "device_tier": {"low", "mid", "high"},
            "locale": {"ru-RU", "en-US"},
            "requested_category": {"laptop", "monitor", "accessory"},
            "outcome": {"purchase", "add_to_cart_only", "abandoned", "no_action"},
        },
        "agent_actions": {
            "action_type": {"understand_query", "search", "filter", "clarify", "recommend", "answer", "abandon_flow"},
        },
        "tool_calls": {
            "tool_name": {"search_products", "filter_products", "get_product_details", "compare_products"},
            "error_type": {"none", "timeout", "empty_result", "invalid_args"},
        },
        "product_events": {
            "event_type": {"impression", "click", "add_to_cart", "purchase", "remove_from_cart"},
        },
        "evaluations": {
            "eval_type": {"offline_task_success", "constraint_satisfaction", "answer_faithfulness"},
            "evaluator": {"rule_based", "llm"},
        },
        "users": {
            "persona": {"budget", "mainstream", "power_user", "gift_buyer"},
        },
    }
    with db_engine.connect() as conn:
        for table, columns in checks.items():
            for column, allowed in columns.items():
                rows = conn.execute(text(f"SELECT DISTINCT {column} FROM {table}")).fetchall()
                observed = {r[0] for r in rows}
                assert observed.issubset(allowed), f"{table}.{column} has unexpected values: {observed - allowed}"


def test_failure_label_source_enum_has_single_app_value():
    """DATA_MODEL.md SS3.11: source has one legal value in the app schema."""
    from backend.app.models.enums import FailureLabelSource

    assert [m.value for m in FailureLabelSource] == ["llm_classifier"]


def test_constraints_json_is_valid_jsonb(db_engine):
    count = _scalar(db_engine, "SELECT count(*) FROM sessions WHERE jsonb_typeof(constraints_json) != 'object'")
    assert count == 0
