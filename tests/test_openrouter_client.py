"""OpenRouterLLMClient: env-var wiring, bounded retry / safe-fallback
behavior, and provenance mapping — all fully offline (no network call, no
real OPENROUTER_API_KEY). The `openai` package is required to import this
module (it's under the optional `llm` extra); tests here are skipped
automatically if it isn't installed, exactly like the rest of the suite
never depends on live LLM availability (Stage 2 review requirement #10).
"""

from __future__ import annotations

import pytest

pytest.importorskip("openai")

from backend.llm.client import FAILURE_TAXONOMY, SessionContext, ToolCallSummary
from backend.llm.openrouter_client import DEFAULT_MODEL, MAX_RETRIES, OpenRouterLLMClient
from backend.llm.provenance import parse_real_llm_version, real_llm_classifier_version


def _make_context() -> SessionContext:
    return SessionContext(
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


def test_requires_api_key_env_var(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # A real .env file may exist in this working directory (local dev
    # convenience — see backend/llm/openrouter_client.py's load_dotenv()
    # call); disable it here so this test verifies "no key in the process
    # environment" regardless of what's on disk.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    with pytest.raises(KeyError):
        OpenRouterLLMClient()


def test_model_defaults_and_is_overridable_via_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert OpenRouterLLMClient().model == DEFAULT_MODEL

    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
    assert OpenRouterLLMClient().model == "anthropic/claude-sonnet-4.5"


def test_model_can_be_passed_explicitly_overriding_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient(model="anthropic/claude-sonnet-4.6")
    assert client.model == "anthropic/claude-sonnet-4.6"


def test_bounded_retries_then_safe_fallback_on_persistent_malformed_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient()

    call_count = {"n": 0}

    def always_fails(context):
        call_count["n"] += 1
        raise ValueError("simulated malformed response")

    monkeypatch.setattr(client, "_call_once", always_fails)
    result = client.classify_failure(_make_context())

    assert call_count["n"] == MAX_RETRIES + 1
    assert client.last_retry_count == MAX_RETRIES
    assert client.last_fallback is True
    assert result.failure_mode == "other"
    assert result.confidence == 0.0
    assert "failed after" in result.evidence_text


def test_recovers_if_a_retry_succeeds(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient()

    attempts = {"n": 0}

    def fails_once_then_succeeds(context):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ValueError("simulated transient malformed response")
        return {"failure_mode": "retrieval_failure", "confidence": 0.8, "evidence_text": "no matching product was found"}

    monkeypatch.setattr(client, "_call_once", fails_once_then_succeeds)
    result = client.classify_failure(_make_context())

    assert client.last_fallback is False
    assert result.failure_mode == "retrieval_failure"
    assert result.confidence == 0.8


def test_every_taxonomy_label_is_a_valid_classify_failure_result(monkeypatch):
    """The client must accept any taxonomy-valid model output, not just
    the ones exercised above."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient()
    for mode in FAILURE_TAXONOMY:
        monkeypatch.setattr(
            client, "_call_once",
            lambda context, m=mode: {"failure_mode": m, "confidence": 0.5, "evidence_text": "evidence"},
        )
        result = client.classify_failure(_make_context())
        assert result.failure_mode == mode


def test_describe_client_maps_openrouter_to_real_llm_provenance(monkeypatch):
    from backend.llm.classification_pipeline import _describe_client

    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient(model="anthropic/claude-sonnet-5")
    classifier_type, classifier_version, is_mock, provider, model, semantic_prompt_version = _describe_client(client)

    assert classifier_type == "real_llm"
    assert is_mock is False
    assert classifier_version == real_llm_classifier_version("openrouter", "anthropic/claude-sonnet-5")
    assert parse_real_llm_version(classifier_version) == ("openrouter", "anthropic/claude-sonnet-5")
    assert provider == "openrouter"
    assert model == "anthropic/claude-sonnet-5"
    assert semantic_prompt_version == client.semantic_prompt_version


def test_classify_semantic_raises_after_exhausted_retries_never_returns_fake_result(monkeypatch):
    """The core reliability requirement for the hybrid redesign: a
    malformed/exhausted semantic call must never silently become a
    normal-looking (e.g. all-false) multi-label prediction — it must raise
    so the caller can record the session as not-evaluated."""
    from backend.llm.openrouter_client import MalformedResponseError

    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient()

    class FakeResponse:
        class choices:
            pass

    def raises_malformed(**kwargs):
        raise ValueError("simulated network failure")

    monkeypatch.setattr(client._client.chat.completions, "create", raises_malformed)

    with pytest.raises(MalformedResponseError):
        client.classify_semantic(_make_context())
    assert client.last_fallback is True


def test_classify_semantic_recovers_if_a_retry_succeeds(monkeypatch):
    import json as _json

    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-not-used")
    client = OpenRouterLLMClient()

    valid_payload = _json.dumps(
        {
            "unnecessary_clarification": {"detected": False, "confidence": 0.8, "evidence_text": "no excess clarification"},
            "wrong_constraint_interpretation": {"detected": True, "confidence": 0.7, "evidence_text": "violated a stated budget"},
            "unsupported_product_claim": {"detected": False, "confidence": 0.9, "evidence_text": "no unsupported claim"},
        }
    )

    class FakeMessage:
        content = valid_payload

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None

    attempts = {"n": 0}

    def fails_once_then_succeeds(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ValueError("simulated transient failure")
        return FakeResponse()

    monkeypatch.setattr(client._client.chat.completions, "create", fails_once_then_succeeds)
    attribution = client.classify_semantic(_make_context())

    assert client.last_fallback is False
    detected = {r.mechanism for r in attribution.results if r.detected}
    assert detected == {"wrong_constraint_interpretation"}


def test_parse_and_validate_semantic_rejects_extra_top_level_field():
    import json as _json

    from backend.llm.openrouter_client import MalformedResponseError, parse_and_validate_semantic

    payload = _json.dumps(
        {
            "unnecessary_clarification": {"detected": False, "confidence": 0.8, "evidence_text": "x"},
            "wrong_constraint_interpretation": {"detected": False, "confidence": 0.8, "evidence_text": "x"},
            "unsupported_product_claim": {"detected": False, "confidence": 0.8, "evidence_text": "x"},
            "extra_field": "should not be here",
        }
    )
    with pytest.raises(MalformedResponseError):
        parse_and_validate_semantic(payload)


def test_parse_and_validate_semantic_rejects_out_of_range_confidence():
    import json as _json

    from backend.llm.openrouter_client import MalformedResponseError, parse_and_validate_semantic

    payload = _json.dumps(
        {
            "unnecessary_clarification": {"detected": False, "confidence": 1.5, "evidence_text": "x"},
            "wrong_constraint_interpretation": {"detected": False, "confidence": 0.8, "evidence_text": "x"},
            "unsupported_product_claim": {"detected": False, "confidence": 0.8, "evidence_text": "x"},
        }
    )
    with pytest.raises(MalformedResponseError):
        parse_and_validate_semantic(payload)


def test_client_never_sends_ground_truth_shaped_fields(monkeypatch):
    """SessionContext has no ground-truth field to begin with (see
    test_session_context_has_no_ground_truth_field), but this guards the
    rendered prompt text itself never mentions the taxonomy-adjacent
    ground-truth vocabulary, in case a future prompt edit introduces it."""
    from backend.llm.prompts.failure_classification import render_user_message

    rendered = render_user_message(_make_context())
    assert "ground_truth" not in rendered
    assert "planted" not in rendered
