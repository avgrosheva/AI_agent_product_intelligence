"""Stage 9 tasks 2/7: pure mapping-correctness and missing-field tests
for backend.connectors.langfuse.mapper — no HTTP, no database. Every
test builds a raw Langfuse trace dict by hand (the same shape
GET /api/public/traces/{id} returns) and asserts on the resulting
IngestSession."""

from __future__ import annotations

from backend.connectors.langfuse.mapper import UnmappableTraceError, map_trace_to_session, resolve_version

import pytest


def _generation(**overrides) -> dict:
    obs = {
        "id": "obs-1",
        "type": "GENERATION",
        "name": "answer_question",
        "startTime": "2026-08-01T00:00:00Z",
        "endTime": "2026-08-01T00:00:02Z",
        "level": "DEFAULT",
        "model": "gpt-4o",
        "input": [{"role": "user", "content": "Where is my order?"}],
        "output": {"role": "assistant", "content": "It shipped yesterday."},
        "usage": {"input": 42, "output": 17, "total": 59},
        "calculatedTotalCost": 0.0031,
    }
    obs.update(overrides)
    return obs


def _trace(**overrides) -> dict:
    trace = {
        "id": "trace-1",
        "sessionId": "session-1",
        "userId": "user-1",
        "timestamp": "2026-08-01T00:00:00Z",
        "release": "v2",
        "tags": ["prod"],
        "metadata": {"ticket_category": "billing"},
        "observations": [_generation()],
    }
    trace.update(overrides)
    return trace


def _map(trace: dict, **mapping_overrides) -> object:
    defaults = {"external_experiment_id": "exp-1", "version_field": "release", "outcome_metadata_key": None}
    defaults.update(mapping_overrides)
    return map_trace_to_session(trace, **defaults)


def test_session_and_experiment_identity_come_from_langfuse_ids():
    session = _map(_trace())
    assert session.external_session_id == "session-1"
    assert session.external_experiment_id == "exp-1"
    assert session.external_user_id == "user-1"


def test_missing_session_id_falls_back_to_trace_id():
    trace = _trace()
    del trace["sessionId"]
    session = _map(trace)
    assert session.external_session_id == "trace-1"


def test_missing_user_id_is_none_not_fabricated():
    trace = _trace()
    del trace["userId"]
    session = _map(trace)
    assert session.external_user_id is None


def test_agent_version_from_configured_field():
    trace = _trace(release="v2", **{"version": "v1-should-be-ignored"})
    session = _map(trace, version_field="release")
    assert session.agent_version == "v2"


def test_agent_version_falls_back_to_other_native_field():
    trace = _trace()
    del trace["release"]
    trace["version"] = "1.4.0"
    session = _map(trace, version_field="release")
    assert session.agent_version == "1.4.0"


def test_agent_version_falls_back_to_unknown_when_neither_field_present():
    trace = _trace()
    del trace["release"]
    session = _map(trace, version_field="release")
    assert session.agent_version == "unknown-version"


def test_chat_shaped_messages_map_one_turn_each():
    session = _map(_trace())
    assert [(m.sender, m.text) for m in session.messages] == [
        ("user", "Where is my order?"),
        ("assistant", "It shipped yesterday."),
    ]
    assert session.messages[0].turn_index == 0
    assert session.messages[1].turn_index == 1


def test_non_chat_shaped_input_falls_back_to_single_stringified_message():
    trace = _trace(observations=[_generation(input="plain text prompt", output="plain text reply")])
    session = _map(trace)
    assert [(m.sender, m.text) for m in session.messages] == [
        ("user", "plain text prompt"),
        ("assistant", "plain text reply"),
    ]


def test_generation_observation_produces_one_tool_call():
    session = _map(_trace())
    assert len(session.actions) == 1
    action = session.actions[0]
    assert action.action_type == "answer_question"
    assert action.latency_ms == 2000
    assert len(action.tool_calls) == 1
    call = action.tool_calls[0]
    assert call.tool_name == "gpt-4o"
    assert call.success is True
    assert call.error_type is None


def test_error_level_observation_maps_to_failed_tool_call_and_error_outcome():
    trace = _trace(observations=[_generation(level="ERROR", statusMessage="rate_limited")])
    session = _map(trace)
    call = session.actions[0].tool_calls[0]
    assert call.success is False
    assert call.error_type == "rate_limited"
    assert session.outcome.label == "error"


def test_no_error_observations_gives_completed_outcome_by_default():
    session = _map(_trace())
    assert session.outcome.label == "completed"


def test_outcome_metadata_key_overrides_technical_status_when_present():
    trace = _trace(metadata={"ticket_category": "billing", "ticket_outcome": "resolved"})
    session = _map(trace, outcome_metadata_key="ticket_outcome")
    assert session.outcome.label == "resolved"


def test_outcome_metadata_key_falls_back_when_key_absent():
    trace = _trace(metadata={"ticket_category": "billing"})
    session = _map(trace, outcome_metadata_key="ticket_outcome")
    assert session.outcome.label == "completed"


def test_usage_and_cost_aggregated_into_session_metrics():
    session = _map(_trace())
    metrics = {m.name: m.value for m in session.metrics}
    assert metrics["prompt_tokens"] == 42.0
    assert metrics["completion_tokens"] == 17.0
    assert metrics["total_tokens"] == 59.0
    assert metrics["cost_usd"] == pytest.approx(0.0031)


def test_missing_usage_and_cost_are_omitted_not_zeroed():
    trace = _trace(observations=[_generation(usage=None, calculatedTotalCost=None)])
    session = _map(trace)
    names = {m.name for m in session.metrics}
    assert names == set()


def test_missing_observations_gives_empty_messages_and_actions():
    trace = _trace(observations=[])
    session = _map(trace)
    assert session.messages == []
    assert session.actions == []
    assert session.outcome.label == "completed"


def test_context_flattens_metadata_and_adds_langfuse_traceability_keys():
    trace = _trace(metadata={"ticket_category": "billing"}, tags=["prod", "regression"], name="support-triage")
    session = _map(trace)
    assert session.context["ticket_category"] == "billing"
    assert session.context["langfuse_trace_id"] == "trace-1"
    assert session.context["langfuse_tags"] == ["prod", "regression"]
    assert session.context["langfuse_trace_name"] == "support-triage"


def test_missing_trace_id_is_unmappable():
    trace = _trace()
    del trace["id"]
    with pytest.raises(UnmappableTraceError):
        _map(trace)


def test_missing_timestamp_is_unmappable():
    trace = _trace()
    del trace["timestamp"]
    with pytest.raises(UnmappableTraceError):
        _map(trace)


def test_resolve_version_helper_used_by_service_for_auto_derivation():
    assert resolve_version({"release": "v3"}, "release") == "v3"
    assert resolve_version({"version": "v3"}, "release") == "v3"
    assert resolve_version({}, "release") == "unknown-version"
