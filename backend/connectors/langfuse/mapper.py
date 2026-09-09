"""Pure mapping from a raw Langfuse trace (already including its nested
`observations` list, as returned by `GET /api/public/traces/{id}`) into
this platform's generic ingestion schema (backend.ingestion.schemas). No
I/O, no database, no HTTP — every function here takes plain dicts and
already-resolved mapping config and returns Pydantic ingestion objects
(or raises UnmappableTraceError for one trace), so it is testable with
plain fixtures and reused identically by both the dry-run preview and the
real import path (backend.connectors.langfuse.service).

Mapping rules (Stage 9 task 2):
  - session / trace id  -> external_session_id: trace.sessionId if
    Langfuse recorded one, else the trace's own id (a session-less
    single-trace import still produces one IngestSession).
  - user id             -> external_user_id: trace.userId, or None.
  - agent/model version -> agent_version: the configured native trace
    field ("release" or "version" — Langfuse's own two fields for this),
    falling back to the other one, then to the literal "unknown-version"
    when neither is present. Never a fabricated real-looking version.
  - messages            -> one IngestMessage per chat turn found in each
    observation's `input`/`output` (list-of-{role,content} when the
    generation is chat-shaped; a single stringified turn otherwise).
  - tool calls          -> one IngestToolCall per GENERATION observation,
    success=False + error_type=statusMessage when observation.level is
    "ERROR" — this is also how errors surface (Langfuse has no separate
    "error" entity; an errored observation IS the error).
  - latency             -> latency_ms on the IngestAction (and its
    tool call, for a GENERATION), computed from the observation's own
    startTime/endTime.
  - token usage / cost  -> session-level IngestMetrics ("prompt_tokens",
    "completion_tokens", "total_tokens", "cost_usd"), summed across every
    observation that actually reported `usage`/`calculatedTotalCost` —
    omitted entirely (not zero) when no observation reported them.
  - metadata/context    -> IngestSession.context: trace.metadata merged
    in directly (flat, so a source system's own domain-specific keys like
    "ticket_category" land exactly where a domain adapter already expects
    them) plus three "langfuse_"-prefixed keys for traceability.
  - outcome/business metrics -> outcome.label: trace.metadata[<configured
    key>] verbatim WHEN that key is present (a real business outcome, iff
    the source system actually attached one); otherwise a technical
    execution status ("completed"/"error") derived purely from whether
    any observation reported level="ERROR" — never a fabricated business
    result. Per-session numeric business metrics are not invented either:
    only usage/cost, which Langfuse itself always reports per generation,
    are added automatically.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.ingestion.schemas import IngestAction, IngestMessage, IngestMetric, IngestOutcome, IngestSession, IngestToolCall


class UnmappableTraceError(Exception):
    """Raised for one trace missing a field the generic schema requires
    with no reasonable fallback (an id or a start timestamp) — the caller
    records the reason and skips that one trace rather than failing the
    whole batch."""


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return str(value)


def resolve_version(trace: dict, version_field: str) -> str:
    other = "version" if version_field != "version" else "release"
    for field_name in (version_field, other):
        value = trace.get(field_name)
        if value:
            return str(value)
    return "unknown-version"


def _resolve_outcome_label(trace: dict, observations: list[dict], outcome_metadata_key: str | None) -> str:
    metadata = trace.get("metadata") or {}
    if outcome_metadata_key and metadata.get(outcome_metadata_key):
        return str(metadata[outcome_metadata_key])
    if any((obs.get("level") or "").upper() == "ERROR" for obs in observations):
        return "error"
    return "completed"


def _as_dict(value: object) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": _stringify(value)}


def _messages_from_observation(obs: dict, turn_counter: list[int]) -> list[IngestMessage]:
    messages: list[IngestMessage] = []
    started_at = _parse_timestamp(obs["startTime"]) if obs.get("startTime") else datetime.now(timezone.utc).replace(tzinfo=None)

    def emit(sender: str, content: object) -> None:
        if content is None:
            return
        text = content if isinstance(content, str) else _stringify(content)
        if not text:
            return
        turn_counter[0] += 1
        messages.append(
            IngestMessage(
                external_message_id=f"{obs['id']}-{sender}-{turn_counter[0]}",
                turn_index=turn_counter[0] - 1,
                sender=sender,
                text=text,
                created_at=started_at,
            )
        )

    input_ = obs.get("input")
    if isinstance(input_, list) and input_ and all(isinstance(m, dict) and "role" in m for m in input_):
        for turn in input_:
            emit(str(turn.get("role", "user")), turn.get("content"))
    elif input_ is not None:
        emit("user", input_)

    output_ = obs.get("output")
    if isinstance(output_, dict) and "role" in output_:
        emit(str(output_.get("role", "assistant")), output_.get("content"))
    elif output_ is not None:
        emit("assistant", output_)

    return messages


def _action_from_observation(obs: dict, index: int) -> IngestAction:
    started_at = _parse_timestamp(obs["startTime"]) if obs.get("startTime") else datetime.now(timezone.utc).replace(tzinfo=None)
    ended_at = _parse_timestamp(obs["endTime"]) if obs.get("endTime") else None
    latency_ms = max(0, int((ended_at - started_at).total_seconds() * 1000)) if ended_at else None
    obs_type = (obs.get("type") or "span").lower()

    tool_calls: list[IngestToolCall] = []
    if obs_type == "generation":
        is_error = (obs.get("level") or "").upper() == "ERROR"
        tool_calls.append(
            IngestToolCall(
                external_tool_call_id=f"{obs['id']}-call",
                tool_name=obs.get("model") or "llm",
                success=not is_error,
                error_type=obs.get("statusMessage") if is_error else None,
                latency_ms=latency_ms,
                input=_as_dict(obs.get("input")),
                output=_as_dict(obs.get("output")),
            )
        )

    return IngestAction(
        external_action_id=str(obs["id"]),
        sequence_index=index,
        action_type=str(obs.get("name") or obs_type),
        started_at=started_at,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
    )


def _usage_and_cost_metrics(observations: list[dict]) -> list[IngestMetric]:
    prompt_tokens = completion_tokens = total_tokens = 0
    total_cost = 0.0
    have_tokens = have_cost = False
    for obs in observations:
        usage = obs.get("usage") or {}
        if usage:
            have_tokens = True
            prompt_tokens += usage.get("input") or usage.get("promptTokens") or 0
            completion_tokens += usage.get("output") or usage.get("completionTokens") or 0
            total_tokens += usage.get("total") or ((usage.get("input") or 0) + (usage.get("output") or 0))
        cost = obs.get("calculatedTotalCost")
        if cost is not None:
            have_cost = True
            total_cost += float(cost)

    metrics: list[IngestMetric] = []
    if have_tokens:
        metrics.append(IngestMetric(name="prompt_tokens", value=float(prompt_tokens)))
        metrics.append(IngestMetric(name="completion_tokens", value=float(completion_tokens)))
        metrics.append(IngestMetric(name="total_tokens", value=float(total_tokens)))
    if have_cost:
        metrics.append(IngestMetric(name="cost_usd", value=total_cost))
    return metrics


def map_trace_to_session(
    trace: dict,
    *,
    external_experiment_id: str,
    version_field: str,
    outcome_metadata_key: str | None,
) -> IngestSession:
    if not trace.get("id"):
        raise UnmappableTraceError("a trace with no 'id' cannot be mapped to a session")
    if not trace.get("timestamp"):
        raise UnmappableTraceError(f"trace {trace.get('id')!r} has no 'timestamp' (required as started_at)")

    observations = sorted(trace.get("observations") or [], key=lambda o: o.get("startTime") or "")

    messages: list[IngestMessage] = []
    actions: list[IngestAction] = []
    turn_counter = [0]
    for i, obs in enumerate(observations):
        messages.extend(_messages_from_observation(obs, turn_counter))
        actions.append(_action_from_observation(obs, i))

    ended_at: datetime | None = None
    if observations and observations[-1].get("endTime"):
        ended_at = _parse_timestamp(observations[-1]["endTime"])
    elif trace.get("latency") is not None:
        ended_at = _parse_timestamp(trace["timestamp"]) + timedelta(seconds=float(trace["latency"]))

    metadata = trace.get("metadata") or {}
    context = {
        **metadata,
        "langfuse_trace_id": trace["id"],
        "langfuse_tags": trace.get("tags") or [],
        "langfuse_trace_name": trace.get("name"),
    }

    return IngestSession(
        external_session_id=str(trace.get("sessionId") or trace["id"]),
        external_experiment_id=external_experiment_id,
        agent_version=resolve_version(trace, version_field),
        external_user_id=str(trace["userId"]) if trace.get("userId") else None,
        started_at=_parse_timestamp(trace["timestamp"]),
        ended_at=ended_at,
        messages=messages,
        actions=actions,
        outcome=IngestOutcome(label=_resolve_outcome_label(trace, observations, outcome_metadata_key), metrics=[]),
        metrics=_usage_and_cost_metrics(observations),
        context=context,
    )
