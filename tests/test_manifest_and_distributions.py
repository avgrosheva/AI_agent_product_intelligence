"""Generator manifest completeness and basic distribution/row-count sanity
checks (DATA_MODEL.md SS5, SS6, SS7)."""

from __future__ import annotations

import json

import pandas as pd

from datagen.constants import EFFECT_PARAMS


def test_manifest_has_seed_row_counts_and_all_five_effect_params(dev_data_dir):
    with open(dev_data_dir / "dev" / "generation_manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["profile"] == "dev"
    assert manifest["seed"] == 42
    assert set(manifest["row_counts"]) == {
        "users", "products", "experiments", "sessions", "messages", "agent_actions",
        "tool_calls", "recommendations", "product_events", "evaluations", "failure_labels",
    }
    assert set(manifest["planted_effects"]) == set(EFFECT_PARAMS)
    for effect_name, params in EFFECT_PARAMS.items():
        assert manifest["planted_effects"][effect_name] == params


def test_row_counts_within_expected_dev_scale(dev_data_dir):
    app_dir = dev_data_dir / "dev" / "application"
    users = pd.read_parquet(app_dir / "users.parquet")
    products = pd.read_parquet(app_dir / "products.parquet")
    sessions = pd.read_parquet(app_dir / "sessions.parquet")

    assert len(users) == 600
    assert len(products) == 150
    assert 1200 < len(sessions) < 3500  # DATA_MODEL.md SS5: ~1,800 target, generous band around it


def test_category_distribution_roughly_matches_catalog_design(dev_data_dir):
    products = pd.read_parquet(dev_data_dir / "dev" / "application" / "products.parquet")
    counts = products.category.value_counts()
    assert counts["laptop"] == 90
    assert counts["monitor"] == 35
    assert counts["accessory"] == 25


def test_requested_category_distribution_is_plausible(dev_data_dir):
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    share = sessions.requested_category.value_counts(normalize=True)
    assert 0.50 < share["laptop"] < 0.70
    assert 0.15 < share["monitor"] < 0.35
    assert 0.08 < share["accessory"] < 0.25


def test_constraint_bucket_distribution_is_plausible(dev_data_dir):
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    bucket = pd.cut(sessions.num_constraints, [-1, 1, 2, 100], labels=["0-1", "2", "3+"])
    share = bucket.value_counts(normalize=True)
    assert 0.30 < share["0-1"] < 0.50
    assert 0.15 < share["2"] < 0.35
    assert 0.25 < share["3+"] < 0.45


def test_prices_and_ratings_are_within_sane_bounds(dev_data_dir):
    products = pd.read_parquet(dev_data_dir / "dev" / "application" / "products.parquet")
    assert (products.price_rub > 0).all()
    assert (products.price_rub < 300_000).all()
    assert products.rating.between(3.0, 5.0).all()
    assert products.margin_pct.between(0.05, 0.40).all()


def test_no_negative_or_absurd_latency_or_cost(dev_data_dir):
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    assert (sessions.total_latency_ms > 0).all()
    assert (sessions.total_cost_usd >= 0).all()
    assert (sessions.total_cost_usd < 1.0).all()  # sanity ceiling for a single chat session


def test_outcome_distribution_has_no_degenerate_category(dev_data_dir):
    """Quality rule (approved docs point 8): distributions shouldn't be
    degenerate/artificial — every outcome should have meaningful representation."""
    sessions = pd.read_parquet(dev_data_dir / "dev" / "application" / "sessions.parquet")
    share = sessions.outcome.value_counts(normalize=True)
    for outcome in ["purchase", "add_to_cart_only", "abandoned", "no_action"]:
        assert share.get(outcome, 0) > 0.03, f"{outcome} is suspiciously rare ({share.get(outcome, 0):.3f})"
