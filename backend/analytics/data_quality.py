"""Data-quality and cross-table reconciliation checks (Stage 1 review
requirement #6). Each check returns a violation count; a report is a list
of these, and Stage 2 acceptance requires every one to be zero on the
generated dataset (or to explain, honestly, why a nonzero count is
expected — see the Stage 2 deliverable report for any such case).

Referential-integrity checks here overlap deliberately with Stage 1's
tests: those tests prove the constraint holds once; this module is a
standalone, reusable report that could be pointed at any load of the data
(e.g. after a future change to the generator or loader), not just a
one-time pytest assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from datagen.constants import PRICE_IN_PER_1K_TOKENS, PRICE_OUT_PER_1K_TOKENS


@dataclass
class CheckResult:
    name: str
    description: str
    violation_count: int
    passed: bool
    notes: str = ""


def _count(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def _run_checks(engine: Engine, checks: list[tuple[str, str]], description: str) -> list[CheckResult]:
    """`checks` is a list of (name, sql) pairs sharing one description."""
    results = []
    for name, sql in checks:
        n = _count(engine, sql)
        results.append(CheckResult(name, description, n, n == 0))
    return results


def _run_named_checks(engine: Engine, checks: list[tuple[str, str, str]]) -> list[CheckResult]:
    """`checks` is a list of (name, sql, description) triples with a
    per-check description (used when the description varies by check)."""
    results = []
    for name, sql, description in checks:
        n = _count(engine, sql)
        results.append(CheckResult(name, description, n, n == 0))
    return results


def check_duplicate_ids(engine: Engine) -> list[CheckResult]:
    tables_and_pks = [
        ("users", "user_id"), ("products", "product_id"), ("experiments", "experiment_id"),
        ("sessions", "session_id"), ("messages", "message_id"), ("agent_actions", "action_id"),
        ("tool_calls", "tool_call_id"), ("recommendations", "rec_id"), ("product_events", "event_id"),
        ("evaluations", "eval_id"), ("session_failure_attributions", "attribution_id"),
    ]
    results = []
    for table, pk in tables_and_pks:
        n = _count(engine, f"SELECT count(*) - count(DISTINCT {pk}) FROM {table}")
        results.append(CheckResult(f"duplicate_ids_{table}", f"Duplicate {pk} values in {table}", n, n == 0))
    return results


def check_negative_values(engine: Engine) -> list[CheckResult]:
    checks = [
        ("negative_session_latency", "SELECT count(*) FROM sessions WHERE total_latency_ms < 0", "Negative sessions.total_latency_ms"),
        ("negative_session_cost", "SELECT count(*) FROM sessions WHERE total_cost_usd < 0", "Negative sessions.total_cost_usd"),
        ("negative_session_tokens", "SELECT count(*) FROM sessions WHERE total_tokens_in < 0 OR total_tokens_out < 0", "Negative sessions.total_tokens_in/out"),
        ("negative_action_latency", "SELECT count(*) FROM agent_actions WHERE latency_ms < 0", "Negative agent_actions.latency_ms"),
        ("negative_tool_call_latency", "SELECT count(*) FROM tool_calls WHERE latency_ms < 0", "Negative tool_calls.latency_ms"),
        ("negative_message_tokens", "SELECT count(*) FROM messages WHERE tokens < 0", "Negative messages.tokens"),
    ]
    return _run_named_checks(engine, checks)


def check_events_outside_session_bounds(engine: Engine) -> list[CheckResult]:
    checks = [
        (
            "product_events_outside_session_bounds",
            """
            SELECT count(*) FROM product_events pe JOIN sessions s ON s.session_id = pe.session_id
            WHERE pe.event_time < s.started_at OR (s.ended_at IS NOT NULL AND pe.event_time > s.ended_at)
            """,
        ),
        (
            "messages_outside_session_bounds",
            """
            SELECT count(*) FROM messages m JOIN sessions s ON s.session_id = m.session_id
            WHERE m.created_at < s.started_at OR (s.ended_at IS NOT NULL AND m.created_at > s.ended_at)
            """,
        ),
        (
            "agent_actions_outside_session_bounds",
            """
            SELECT count(*) FROM agent_actions a JOIN sessions s ON s.session_id = a.session_id
            WHERE a.started_at < s.started_at OR (s.ended_at IS NOT NULL AND a.started_at > s.ended_at)
            """,
        ),
    ]
    return _run_checks(engine, checks, "Child event timestamp outside parent session's [started_at, ended_at]")


def check_invalid_event_ordering(engine: Engine) -> list[CheckResult]:
    """Funnel-step ordering: a later funnel event must not time-precede the
    step before it, for the same session+product."""
    checks = [
        (
            "click_before_impression",
            """
            SELECT count(*) FROM product_events c
            WHERE c.event_type = 'click' AND NOT EXISTS (
                SELECT 1 FROM product_events i
                WHERE i.session_id = c.session_id AND i.product_id = c.product_id
                  AND i.event_type = 'impression' AND i.event_time <= c.event_time
            )
            """,
        ),
        (
            "add_to_cart_before_click",
            """
            SELECT count(*) FROM product_events a
            WHERE a.event_type = 'add_to_cart' AND NOT EXISTS (
                SELECT 1 FROM product_events c
                WHERE c.session_id = a.session_id AND c.product_id = a.product_id
                  AND c.event_type = 'click' AND c.event_time <= a.event_time
            )
            """,
        ),
        (
            "purchase_before_add_to_cart",
            """
            SELECT count(*) FROM product_events p
            WHERE p.event_type = 'purchase' AND NOT EXISTS (
                SELECT 1 FROM product_events a
                WHERE a.session_id = p.session_id AND a.product_id = p.product_id
                  AND a.event_type = 'add_to_cart' AND a.event_time <= p.event_time
            )
            """,
        ),
    ]
    return _run_checks(engine, checks, "Malformed funnel: a step occurred without its required predecessor")


def check_impossible_outcomes(engine: Engine) -> list[CheckResult]:
    checks = [
        (
            "purchase_outcome_without_purchase_event",
            """
            SELECT count(*) FROM sessions s
            WHERE s.outcome = 'purchase' AND NOT EXISTS (
                SELECT 1 FROM product_events pe WHERE pe.session_id = s.session_id AND pe.event_type = 'purchase'
            )
            """,
        ),
        (
            "purchase_event_without_purchase_outcome",
            """
            SELECT count(DISTINCT s.session_id) FROM sessions s
            JOIN product_events pe ON pe.session_id = s.session_id AND pe.event_type = 'purchase'
            WHERE s.outcome != 'purchase'
            """,
        ),
        (
            "add_to_cart_only_outcome_without_cart_event",
            """
            SELECT count(*) FROM sessions s
            WHERE s.outcome = 'add_to_cart_only' AND NOT EXISTS (
                SELECT 1 FROM product_events pe WHERE pe.session_id = s.session_id AND pe.event_type = 'add_to_cart'
            )
            """,
        ),
        (
            "abandoned_outcome_with_purchase_or_cart_event",
            """
            SELECT count(DISTINCT s.session_id) FROM sessions s
            JOIN product_events pe ON pe.session_id = s.session_id
            WHERE s.outcome = 'abandoned' AND pe.event_type IN ('purchase', 'add_to_cart')
            """,
        ),
    ]
    return _run_checks(engine, checks, "sessions.outcome contradicts its product_events")


def check_recommendation_click_reconciliation(engine: Engine) -> list[CheckResult]:
    checks = [
        (
            "recommendation_clicked_without_click_event",
            """
            SELECT count(*) FROM recommendations r
            WHERE r.clicked = true AND NOT EXISTS (
                SELECT 1 FROM product_events pe
                WHERE pe.session_id = r.session_id AND pe.product_id = r.product_id AND pe.event_type = 'click'
            )
            """,
        ),
        (
            "click_event_without_recommendation_clicked_flag",
            """
            SELECT count(*) FROM product_events pe
            WHERE pe.event_type = 'click' AND NOT EXISTS (
                SELECT 1 FROM recommendations r
                WHERE r.session_id = pe.session_id AND r.product_id = pe.product_id AND r.clicked = true
            )
            """,
        ),
    ]
    return _run_checks(engine, checks, "recommendations.clicked disagrees with product_events click rows")


def check_no_orphan_relationships(engine: Engine) -> list[CheckResult]:
    """Belt-and-suspenders: Postgres FK constraints already make these
    structurally impossible for data loaded via datagen/load_to_postgres.py;
    this check proves it live rather than assuming the constraint is in
    place, so it still catches a future load path that bypasses the ORM."""
    checks = [
        ("orphan_sessions_user", "SELECT count(*) FROM sessions s LEFT JOIN users u ON s.user_id=u.user_id WHERE u.user_id IS NULL"),
        ("orphan_messages_session", "SELECT count(*) FROM messages m LEFT JOIN sessions s ON m.session_id=s.session_id WHERE s.session_id IS NULL"),
        ("orphan_tool_calls_action", "SELECT count(*) FROM tool_calls tc LEFT JOIN agent_actions a ON tc.action_id=a.action_id WHERE a.action_id IS NULL"),
        ("orphan_recommendations_product", "SELECT count(*) FROM recommendations r LEFT JOIN products p ON r.product_id=p.product_id WHERE p.product_id IS NULL"),
    ]
    return _run_checks(engine, checks, "Orphaned child row with no matching parent")


def check_users_crossing_arms(engine: Engine) -> CheckResult:
    n = _count(
        engine,
        """
        SELECT count(*) FROM (
            SELECT user_id, experiment_id FROM sessions
            GROUP BY user_id, experiment_id HAVING count(DISTINCT agent_version) > 1
        ) t
        """,
    )
    return CheckResult("users_crossing_arms", "Users assigned to both v1 and v2 within one experiment", n, n == 0)


def check_cost_reconciles_with_token_pricing(engine: Engine, tolerance_usd: float = 0.01) -> CheckResult:
    """Recomputes expected cost from stored token counts and the generator's
    published pricing constants (datagen/constants.py — public generation
    parameters, not the isolated ground-truth artifact) and compares to the
    stored total_cost_usd."""
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT session_id, total_tokens_in, total_tokens_out, total_cost_usd::float8 AS total_cost_usd FROM sessions"), conn)
    expected = (df.total_tokens_in / 1000.0) * PRICE_IN_PER_1K_TOKENS + (df.total_tokens_out / 1000.0) * PRICE_OUT_PER_1K_TOKENS
    diff = (df.total_cost_usd - expected).abs()
    n_violations = int((diff > tolerance_usd).sum())
    return CheckResult(
        "cost_reconciles_with_token_pricing",
        f"sessions.total_cost_usd matches tokens x published pricing within ${tolerance_usd}",
        n_violations,
        n_violations == 0,
        notes=f"max abs diff observed: ${diff.max():.6f}",
    )


def check_num_turns_reconciles_with_messages(engine: Engine) -> CheckResult:
    """num_turns is documented (DATA_MODEL.md SS3.4) as the count of user
    turns; reconciles it against a direct recount of distinct turn_index
    values among each session's user-sent messages."""
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT s.session_id, s.num_turns,
                       (SELECT count(DISTINCT m.turn_index) FROM messages m
                        WHERE m.session_id = s.session_id AND m.sender = 'user') AS recomputed_turns
                FROM sessions s
                """
            ),
            conn,
        )
    n_violations = int((df.num_turns != df.recomputed_turns).sum())
    return CheckResult(
        "num_turns_reconciles_with_messages",
        "sessions.num_turns equals the count of distinct user-message turn_index values",
        n_violations,
        n_violations == 0,
    )


def run_full_report(engine: Engine) -> list[CheckResult]:
    results: list[CheckResult] = []
    results += check_duplicate_ids(engine)
    results += check_negative_values(engine)
    results += check_events_outside_session_bounds(engine)
    results += check_invalid_event_ordering(engine)
    results += check_impossible_outcomes(engine)
    results += check_recommendation_click_reconciliation(engine)
    results += check_no_orphan_relationships(engine)
    results.append(check_users_crossing_arms(engine))
    results.append(check_cost_reconciles_with_token_pricing(engine))
    results.append(check_num_turns_reconciles_with_messages(engine))
    return results


def report_to_dataframe(results: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame([{"check": r.name, "description": r.description, "violations": r.violation_count, "passed": r.passed, "notes": r.notes} for r in results])
