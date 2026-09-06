"""Classifier output validation and ground-truth leakage prevention
(Stage 2 review requirements #6, #10)."""

from __future__ import annotations

import inspect

import pytest

from backend.llm import context_builder as context_builder_module
from backend.llm.client import FAILURE_TAXONOMY, FailureClassification, SessionContext, ToolCallSummary
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


def test_classification_pipeline_writes_only_llm_classifier_source():
    import inspect as _inspect

    from backend.llm import classification_pipeline

    source = _inspect.getsource(classification_pipeline)
    assert '"source": "llm_classifier"' in source
    assert "ground_truth" not in source
