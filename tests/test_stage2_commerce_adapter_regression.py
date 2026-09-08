"""Stage 2 (domain-agnostic core) regression proof: the commerce
domain/adapter refactor (guardrails moved to data-driven definitions,
mechanism tuples sourced from a registry, segment dimensions and metric
value-columns relocated to backend/domains/commerce/) produces exactly the
same results as before the refactor.

Both tests below are marked slow: they read the ALREADY-LOADED
demo-profile Postgres database (the same one
scripts/run_stage5_demo_validation.py uses) rather than generating/loading
their own — running them requires the demo dataset to already be loaded
(`datagen.load_to_postgres --profile demo`), which is the documented setup
step, not something a normal fast `pytest` run should require.

Deliberately do NOT use backend.app.dependencies' cached get_engine()/
get_base_df() or backend.app.db.get_database_url() here: tests/conftest.py
forces DATABASE_URL to the isolated test database for every pytest run
(Stage 1's test/demo DB isolation fix), so those functions always resolve
to the small dev-scale test database inside a pytest process, never the
demo one — using them here would silently test the wrong dataset. Instead
this file builds its own engine directly from
backend.app.db.DEFAULT_DATABASE_URL (the literal demo database
"ai_agent_pi"), overridable via DEMO_DATABASE_URL for a non-default setup.
"""

from __future__ import annotations

import os

import pytest


def _demo_engine():
    from sqlalchemy import create_engine

    from backend.app.db import DEFAULT_DATABASE_URL

    return create_engine(os.environ.get("DEMO_DATABASE_URL", DEFAULT_DATABASE_URL))


@pytest.mark.slow
def test_guardrails_match_known_demo_scale_values():
    """Fixed reference values captured from the live demo dataset right
    after the Stage 2 guardrail refactor (data-driven GuardrailDefinition
    list + generic evaluate_guardrails) — proves the commerce adapter
    (backend.domains.commerce.guardrails.COMMERCE_GUARDRAILS) reproduces
    the same three checks the old hardcoded check_guardrails() body did."""
    from backend.analytics.sql_runner import run_sql_file
    from backend.investigation.recommend import check_guardrails

    df = run_sql_file(_demo_engine(), "session_level_base.sql")
    report = check_guardrails(df)
    by_name = {c.name: c for c in report.checks}

    assert set(by_name) == {"p95_latency", "tool_error_rate", "cost_per_session"}

    p95 = by_name["p95_latency"]
    assert p95.v1_value == pytest.approx(2181.75, abs=1.0)
    assert p95.v2_value == pytest.approx(2950.0, abs=50.0)
    assert p95.breached is True

    tool_err = by_name["tool_error_rate"]
    assert tool_err.v1_value == pytest.approx(0.0626, abs=0.005)
    assert tool_err.v2_value == pytest.approx(0.0640, abs=0.005)
    assert tool_err.breached is False

    cost = by_name["cost_per_session"]
    assert cost.v1_value == pytest.approx(0.00526, abs=0.0005)
    assert cost.v2_value == pytest.approx(0.00535, abs=0.0005)
    assert cost.breached is False

    assert report.any_breach is True


@pytest.mark.slow
def test_investigation_hold_verdict_unchanged_at_demo_scale():
    """The flagship experiment's primary (abandonment) lens must still
    return verdict="hold" with the p95_latency guardrail blocking — the
    documented demo finding this whole project is built to reproduce —
    after every Stage 2 relocation (mechanisms, guardrails, segment
    dimensions, metric value-columns into backend/domains/commerce/)."""
    import pandas as pd
    from sqlalchemy import text

    from backend.analytics.sql_runner import run_sql_file
    from backend.llm.client import FAILURE_MECHANISMS
    from backend.investigation.pipeline import run_investigation

    engine = _demo_engine()
    base_df = run_sql_file(engine, "session_level_base.sql")
    with engine.connect() as conn:
        actions_df = pd.read_sql(
            text("SELECT session_id, sequence_index, action_type::text AS action_type FROM agent_actions"), conn
        )
        long_df = pd.read_sql(
            text("SELECT session_id, failure_mode::text AS failure_mode, detected FROM session_failure_attributions"), conn
        )
    if long_df.empty:
        wide = pd.DataFrame(columns=["session_id", *FAILURE_MECHANISMS])
    else:
        wide = long_df.pivot_table(index="session_id", columns="failure_mode", values="detected", aggfunc="first")
        wide = wide.reindex(columns=list(FAILURE_MECHANISMS)).reset_index()

    result = run_investigation(base_df, actions_df, wide, primary_metric_name="abandonment_rate")

    assert result.recommendation.verdict == "hold"
    assert "p95_latency" in result.recommendation.blocking_guardrails
    assert result.guardrails.any_breach is True
