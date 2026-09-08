"""Classifier output validation and ground-truth leakage prevention
(Stage 2 review requirements #6, #10)."""

from __future__ import annotations

import inspect

import pytest

from backend.llm import context_builder as context_builder_module
from backend.llm.client import (
    FAILURE_TAXONOMY,
    SEMANTIC_MECHANISMS,
    FailureClassification,
    MechanismResult,
    ProductEvidence,
    SemanticAttribution,
    SessionContext,
    ToolCallSummary,
)
from backend.llm.mock_client import RuleBasedMockClient


def _make_context(**overrides) -> SessionContext:
    defaults = dict(
        session_id="s1",
        transcript=(("user", "looking for a laptop"),),
        action_sequence=("understand_query", "search", "recommend"),
        tool_calls=(ToolCallSummary(tool_name="search_products", success=True, error_type="none", result_count=5),),
        num_constraints=1,
        requested_category="laptop",
        top_recommendation_satisfies_constraints=True,
        any_shown_recommendation_satisfies_constraints=True,
        outcome="purchase",
    )
    defaults.update(overrides)
    return SessionContext(**defaults)


def test_failure_classification_rejects_unknown_taxonomy_value():
    with pytest.raises(ValueError):
        FailureClassification(failure_mode="not_a_real_mode", confidence=0.5, evidence_text="x")


def test_mock_client_always_returns_a_taxonomy_member():
    client = RuleBasedMockClient()
    contexts = [
        _make_context(),
        _make_context(action_sequence=("understand_query", "search", "clarify", "search", "recommend"), num_constraints=4),
        _make_context(top_recommendation_satisfies_constraints=False, any_shown_recommendation_satisfies_constraints=False, num_constraints=2),
        _make_context(action_sequence=("understand_query", "search", "search", "recommend"), num_constraints=2),
        _make_context(action_sequence=(), transcript=(), tool_calls=(), num_constraints=0, top_recommendation_satisfies_constraints=None, any_shown_recommendation_satisfies_constraints=None, outcome="abandoned"),
    ]
    for ctx in contexts:
        result = client.classify_failure(ctx)
        assert result.failure_mode in FAILURE_TAXONOMY
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.evidence_text, str) and len(result.evidence_text) > 0


def test_mock_client_is_deterministic():
    client = RuleBasedMockClient()
    ctx = _make_context(action_sequence=("understand_query", "search", "clarify", "search", "recommend"), num_constraints=4)
    r1 = client.classify_failure(ctx)
    r2 = client.classify_failure(ctx)
    assert r1 == r2


def test_mock_client_unnecessary_clarification_requires_three_plus_constraints():
    client = RuleBasedMockClient()
    with_clarify_low_constraints = _make_context(action_sequence=("understand_query", "search", "clarify", "search", "recommend"), num_constraints=1)
    result = client.classify_failure(with_clarify_low_constraints)
    assert result.failure_mode != "unnecessary_clarification"


def test_mock_client_distinguishes_wrong_constraint_from_retrieval_failure():
    client = RuleBasedMockClient()
    good_match_existed = _make_context(top_recommendation_satisfies_constraints=False, any_shown_recommendation_satisfies_constraints=True, num_constraints=2)
    no_match_existed = _make_context(top_recommendation_satisfies_constraints=False, any_shown_recommendation_satisfies_constraints=False, num_constraints=2)
    assert client.classify_failure(good_match_existed).failure_mode == "wrong_constraint_interpretation"
    assert client.classify_failure(no_match_existed).failure_mode == "retrieval_failure"


def test_session_context_has_no_ground_truth_field():
    """Structural guard (Stage 2 review requirement #6): the dataclass
    itself must have no field a future coding mistake could populate with
    ground truth."""
    field_names = set(SessionContext.__dataclass_fields__)
    forbidden = {"ground_truth_scenario", "ground_truth_failure_mode", "planted_scenario", "generator_effect", "effect_name"}
    assert field_names.isdisjoint(forbidden)


def test_product_evidence_has_no_internal_business_field():
    """Structural guard for the field ProductEvidence added to
    SessionContext (hybrid multi-label redesign, for unsupported_product_
    claim): margin_pct is real product data but internal business
    information no agent could plausibly have seen — it must never be a
    field a future coding mistake could populate."""
    field_names = set(ProductEvidence.__dataclass_fields__)
    assert "margin_pct" not in field_names


def test_context_builder_products_query_never_selects_margin_pct():
    source = inspect.getsource(context_builder_module._load_raw_tables)
    assert "margin_pct" not in source


def test_context_builder_never_reads_validation_artifact_or_generator_internals():
    """Structural guard: context_builder.py's actual query-building code
    must never reference the validation artifact or datagen internals."""
    functions = [context_builder_module._load_raw_tables, context_builder_module.build_all_contexts]
    for fn in functions:
        source = inspect.getsource(fn)
        assert "validation_ground_truth" not in source
        assert "ground_truth" not in source
        assert "datagen" not in source


def test_context_builder_sql_only_selects_from_application_tables():
    source = inspect.getsource(context_builder_module._load_raw_tables)
    for table in ["sessions", "messages", "agent_actions", "tool_calls", "recommendations"]:
        assert f"FROM {table}" in source or f"FROM {table} " in source


def test_classification_pipeline_never_reads_ground_truth():
    import inspect as _inspect

    from backend.llm import classification_pipeline

    source = _inspect.getsource(classification_pipeline)
    assert "ground_truth" not in source


def _make_product(**overrides) -> ProductEvidence:
    defaults = dict(
        product_id="p1", rank_position=1, satisfies_constraints=True, category="laptop",
        brand="Acme", price_rub=50000, ram_gb=16, storage_gb=512, weight_kg=1.5,
        cpu_tier="mid", gpu_tier="mid", screen_in=15.6, use_case_tags=("programming",),
        rating=4.5, in_stock=True,
    )
    defaults.update(overrides)
    return ProductEvidence(**defaults)


def test_mechanism_result_rejects_unknown_mechanism():
    with pytest.raises(ValueError):
        MechanismResult(mechanism="not_a_real_mechanism", detected=True, confidence=0.5, evidence_text="x")


def test_mechanism_result_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        MechanismResult(mechanism="unnecessary_clarification", detected=True, confidence=1.5, evidence_text="x")


def test_semantic_attribution_requires_exactly_the_three_semantic_mechanisms_in_order():
    with pytest.raises(ValueError):
        SemanticAttribution(
            results=(MechanismResult("unnecessary_clarification", False, 0.5, "x"),)
        )


def test_mock_client_classify_semantic_returns_all_three_mechanisms():
    client = RuleBasedMockClient()
    ctx = _make_context()
    attribution = client.classify_semantic(ctx)
    assert tuple(r.mechanism for r in attribution.results) == SEMANTIC_MECHANISMS
    for r in attribution.results:
        assert isinstance(r.detected, bool)
        assert 0.0 <= r.confidence <= 1.0


def test_mock_client_semantic_all_false_when_nothing_observable():
    client = RuleBasedMockClient()
    ctx = _make_context(
        action_sequence=("understand_query", "search", "recommend"),
        num_constraints=1,
        recommended_products=(_make_product(),),
    )
    attribution = client.classify_semantic(ctx)
    assert all(r.detected is False for r in attribution.results)


def test_mock_client_semantic_can_detect_multiple_mechanisms_simultaneously():
    """A session can legitimately have more than one semantic mechanism
    detected — the hybrid multi-label redesign's core premise."""
    client = RuleBasedMockClient()
    ctx = _make_context(
        action_sequence=("understand_query", "search", "clarify", "search", "recommend"),
        num_constraints=4,
        top_recommendation_satisfies_constraints=False,
        any_shown_recommendation_satisfies_constraints=True,
        recommended_products=(
            _make_product(rank_position=1, satisfies_constraints=False, use_case_tags=()),
            _make_product(rank_position=2, satisfies_constraints=True),
        ),
        transcript=(("user", "looking for a laptop"), ("agent", "This one is also great for gaming.")),
    )
    attribution = client.classify_semantic(ctx)
    detected = {r.mechanism for r in attribution.results if r.detected}
    assert detected == {"unnecessary_clarification", "wrong_constraint_interpretation", "unsupported_product_claim"}
