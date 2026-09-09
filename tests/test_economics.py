"""Stage 7 tasks 5-6/8: deterministic economics — cost/session, cost/
success, incremental cost, and business impact — computed purely from
already-available columns, with every field independently null when its
underlying data isn't there (never invented)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.economics.compute import compute_economics
from backend.economics.config import EconomicsConfig


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_returns_none_when_domain_declares_no_economics_config():
    df = _df([{"agent_version": "v1", "converted": 1}])
    assert compute_economics(df, None) is None


def test_cost_per_session_and_per_success_are_computed_correctly():
    df = _df(
        [
            {"agent_version": "v1", "converted": 1, "cost": 1.0},
            {"agent_version": "v1", "converted": 0, "cost": 2.0},
            {"agent_version": "v2", "converted": 1, "cost": 3.0},
            {"agent_version": "v2", "converted": 1, "cost": 5.0},
        ]
    )
    config = EconomicsConfig(cost_column="cost", success_column="converted", value_column=None)
    result = compute_economics(df, config)

    assert result.cost_per_session_v1 == pytest.approx(1.5)  # mean(1.0, 2.0)
    assert result.cost_per_session_v2 == pytest.approx(4.0)  # mean(3.0, 5.0)
    assert result.cost_per_success_v1 == pytest.approx(1.0)  # only the converted=1 row
    assert result.cost_per_success_v2 == pytest.approx(4.0)  # mean(3.0, 5.0), both converted
    assert result.estimated_incremental_cost_per_session == pytest.approx(2.5)  # 4.0 - 1.5


def test_value_and_business_impact_null_when_value_column_absent():
    df = _df([{"agent_version": "v1", "converted": 1, "cost": 1.0}, {"agent_version": "v2", "converted": 1, "cost": 1.0}])
    config = EconomicsConfig(cost_column="cost", success_column="converted", value_column="revenue")  # declared but not in df
    result = compute_economics(df, config)

    assert result.value_per_success_v1 is None
    assert result.value_per_success_v2 is None
    assert result.estimated_business_impact_per_session is None
    assert "revenue/value data unavailable" in " ".join(result.notes)
    # cost figures are still computed even though value is unavailable —
    # each field degrades independently.
    assert result.cost_per_session_v1 is not None


def test_business_impact_computed_when_all_columns_present():
    # v1: 50% success, value=10 per success, cost=1 per session -> net = 0.5*10 - 1 = 4.0
    # v2: 100% success, value=10 per success, cost=2 per session -> net = 1.0*10 - 2 = 8.0
    # impact = 8.0 - 4.0 = 4.0
    df = _df(
        [
            {"agent_version": "v1", "converted": 1, "cost": 1.0, "revenue": 10.0},
            {"agent_version": "v1", "converted": 0, "cost": 1.0, "revenue": None},
            {"agent_version": "v2", "converted": 1, "cost": 2.0, "revenue": 10.0},
            {"agent_version": "v2", "converted": 1, "cost": 2.0, "revenue": 10.0},
        ]
    )
    config = EconomicsConfig(cost_column="cost", success_column="converted", value_column="revenue")
    result = compute_economics(df, config)

    assert result.estimated_business_impact_per_session == pytest.approx(4.0)


def test_cost_data_absent_still_returns_a_result_with_null_cost_fields():
    df = _df([{"agent_version": "v1", "converted": 1}, {"agent_version": "v2", "converted": 1}])
    config = EconomicsConfig(cost_column="cost_usd", success_column="converted", value_column=None)  # "cost_usd" not in df
    result = compute_economics(df, config)

    assert result is not None
    assert result.cost_per_session_v1 is None
    assert result.cost_per_session_v2 is None
    assert result.estimated_incremental_cost_per_session is None
    assert "cost data unavailable" in " ".join(result.notes)


def test_commerce_economics_config_is_fully_populated():
    from backend.domains.commerce.adapter import CommerceAdapter

    config = CommerceAdapter().economics_config()
    assert config.cost_column == "total_cost_usd"
    assert config.success_column == "converted"
    assert config.value_column == "revenue_usd"


def test_support_economics_config_declares_success_column_that_always_exists():
    from backend.domains.support.adapter import SupportAdapter

    config = SupportAdapter(engine=None).economics_config()
    assert config.success_column == "resolved"


def test_commerce_release_evaluation_includes_real_economics(api_client, experiment_id):
    resp = api_client.post(f"/api/v1/domains/commerce/experiments/{experiment_id}/release-evaluations?primary_metric=abandonment_rate")
    assert resp.status_code == 201
    economics = resp.json()["economics"]
    assert economics is not None
    assert economics["cost_per_session_v1"] is not None
    assert economics["cost_per_session_v2"] is not None
    # commerce has real revenue data -> business impact is a real number, not null
    assert economics["estimated_business_impact_per_session"] is not None


def test_support_release_evaluation_has_null_value_fields_when_no_cost_data_ingested(api_client, support_project_id):
    """Stage 7 task 6: the support fixtures used elsewhere in this suite
    never ingest a cost_usd/revenue_usd metric, so economics must come
    back with null cost/value/impact fields rather than inventing numbers
    — never a crash, never a fabricated figure."""
    import uuid

    tag = f"econ-{uuid.uuid4().hex[:8]}"
    payload = {
        "domain": "support",
        "experiments": [{"external_experiment_id": f"exp-{tag}", "name": f"Econ Test {tag}", "control_version": "v1", "treatment_version": "v2"}],
        "sessions": [
            {
                "external_session_id": f"{tag}-s{i}",
                "external_experiment_id": f"exp-{tag}",
                "agent_version": "v1" if i % 2 == 0 else "v2",
                "external_user_id": f"user-{i}",
                "started_at": "2026-07-01T00:00:00",
                "messages": [],
                "actions": [],
                "outcome": {"label": "resolved", "metrics": []},
                "metrics": [],
                "context": {},
            }
            for i in range(24)
        ],
    }
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": support_project_id})
    assert resp.status_code == 201
    experiments = api_client.get(f"/api/v1/domains/support/experiments?project_id={support_project_id}").json()["experiments"]
    exp_id = next(e["experiment_id"] for e in experiments if e["name"] == f"Econ Test {tag}")

    eval_resp = api_client.post(f"/api/v1/domains/support/experiments/{exp_id}/release-evaluations?primary_metric=resolution_rate&project_id={support_project_id}")
    assert eval_resp.status_code == 201
    economics = eval_resp.json()["economics"]
    assert economics is not None  # support DOES declare a config (success_column="resolved" always exists)
    assert economics["cost_per_session_v1"] is None
    assert economics["cost_per_session_v2"] is None
    assert economics["estimated_business_impact_per_session"] is None
