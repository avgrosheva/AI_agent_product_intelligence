"""Real LLM classifier via OpenRouter, using the OpenAI-compatible chat
completions API (AI_EVALUATION.md SS3). Requires OPENROUTER_API_KEY and the
optional `openai` package (`pip install -e ".[llm]"`) — neither is imported
by anything else in the codebase, so the test suite and the
RuleBasedMockClient path never depend on this module or on live API
availability (Stage 2 review requirement #10).

This is a separate, reproducible demo/evaluation path: run
`python -m scripts.run_classification --client openrouter` with a real key
configured to populate failure_labels via this client instead of the mock,
or `python -m scripts.run_real_llm_evaluation` to run it over a bounded
stratified subset and score against ground truth offline.

Nothing outside this module knows OpenRouter is involved — it implements
the same LLMClient protocol as RuleBasedMockClient, so the rest of the
application (classification_pipeline, Investigation, the API) stays
provider-agnostic.
"""

from __future__ import annotations

import json
import os
import time

from backend.llm.client import (
    FAILURE_TAXONOMY,
    SEMANTIC_MECHANISMS,
    FailureClassification,
    MechanismResult,
    SemanticAttribution,
    SessionContext,
)
from backend.llm.prompts.failure_classification import PROMPT_VERSION, SYSTEM_PROMPT, render_user_message
from backend.llm.prompts.semantic_attribution import (
    PROMPT_VERSION as SEMANTIC_PROMPT_VERSION,
    SYSTEM_PROMPT as SEMANTIC_SYSTEM_PROMPT,
    render_user_message as render_semantic_user_message,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# anthropic/claude-sonnet-5 via OpenRouter: current Claude Sonnet-class
# model, a deliberate balance of classification quality, structured-output
# reliability, latency, and cost for a per-session classification task —
# not the flagship Opus tier, not an older/cheaper Haiku-class model.
# Override with OPENROUTER_MODEL without touching this file.
DEFAULT_MODEL = "anthropic/claude-sonnet-5"

# Raised to 900 after the first 200-session benchmark showed 25/200
# malformed responses (empty content / truncated JSON), almost all
# consistent with the model exhausting a 300-token budget on invisible
# reasoning before ever writing the JSON payload. Reasoning is also
# disabled outright below (OpenRouter's unified `reasoning.effort: "none"`
# — see reasoning-tokens docs; `reasoning.max_tokens` is not used instead
# because OpenRouter enforces a 1024-token floor for Anthropic models,
# which would cost more than it saves for a one-sentence classification).
MAX_OUTPUT_TOKENS = 900
REASONING_CONFIG = {"effort": "none"}

MAX_RETRIES = 2
_REQUIRED_KEYS = ("failure_mode", "confidence", "evidence_text")


class MalformedResponseError(Exception):
    """Raised internally when a response fails schema/taxonomy validation, so classify_failure's retry loop has one exception type to catch and re-raise everything else it doesn't understand."""


def build_chat_kwargs(model: str, context: SessionContext) -> dict:
    """The exact request shape sent to /chat/completions — factored out so
    scripts/run_llm_benchmark_200.py sends byte-for-byte the same request
    OpenRouterLLMClient does, instead of maintaining a second copy that
    could silently drift (e.g. forgetting the reasoning/max_tokens fix)."""
    return dict(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": REASONING_CONFIG},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_user_message(context)},
        ],
    )


def parse_and_validate(text: str | None) -> dict:
    """Strict parse: exactly the three required fields, an approved
    taxonomy label, confidence in [0.0, 1.0], and non-empty evidence_text.
    Raises MalformedResponseError on any violation so the caller's retry
    loop has one exception type to catch, and a malformed response can
    never silently pass through as a normal class prediction."""
    if text is None:
        raise MalformedResponseError("response content is empty (None)")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError(f"invalid JSON: {exc} (raw content: {text!r})") from exc
    if not isinstance(parsed, dict):
        raise MalformedResponseError(f"response is not a JSON object: {parsed!r}")
    extra_keys = set(parsed) - set(_REQUIRED_KEYS)
    if extra_keys:
        raise MalformedResponseError(f"response has unsupported extra fields {extra_keys}: {parsed!r}")
    if not all(k in parsed for k in _REQUIRED_KEYS):
        raise MalformedResponseError(f"response missing required keys {_REQUIRED_KEYS}: {parsed!r}")
    if parsed["failure_mode"] not in FAILURE_TAXONOMY:
        raise MalformedResponseError(f"'{parsed['failure_mode']}' is not in the approved taxonomy")
    try:
        confidence = float(parsed["confidence"])
    except (TypeError, ValueError) as exc:
        raise MalformedResponseError(f"confidence is not a number: {parsed['confidence']!r}") from exc
    if not (0.0 <= confidence <= 1.0):
        raise MalformedResponseError(f"confidence {confidence} outside [0.0, 1.0]")
    evidence_text = parsed["evidence_text"]
    if not isinstance(evidence_text, str) or not evidence_text.strip():
        raise MalformedResponseError(f"evidence_text is empty: {evidence_text!r}")
    return {"failure_mode": parsed["failure_mode"], "confidence": confidence, "evidence_text": evidence_text}


def build_semantic_chat_kwargs(model: str, context: SessionContext) -> dict:
    """Request shape for the ONE semantic multi-label call per session —
    same reliability configuration as build_chat_kwargs (reasoning
    disabled, 900-token budget), different prompt/schema."""
    return dict(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"reasoning": REASONING_CONFIG},
        messages=[
            {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
            {"role": "user", "content": render_semantic_user_message(context)},
        ],
    )


def parse_and_validate_semantic(text: str | None) -> dict:
    """Strict parse for the semantic multi-label response: exactly the
    three named mechanism keys (SEMANTIC_MECHANISMS), each an object with
    exactly detected (bool) / confidence (float in [0,1]) / evidence_text
    (non-empty str), and no other top-level or per-mechanism fields.
    Raises MalformedResponseError on any violation — a malformed response
    can never silently pass through as a normal multi-label prediction."""
    if text is None:
        raise MalformedResponseError("response content is empty (None)")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError(f"invalid JSON: {exc} (raw content: {text!r})") from exc
    if not isinstance(parsed, dict):
        raise MalformedResponseError(f"response is not a JSON object: {parsed!r}")
    if set(parsed) != set(SEMANTIC_MECHANISMS):
        raise MalformedResponseError(f"expected exactly {SEMANTIC_MECHANISMS} as top-level keys, got {set(parsed)}: {parsed!r}")
    result = {}
    for mech in SEMANTIC_MECHANISMS:
        entry = parsed[mech]
        if not isinstance(entry, dict):
            raise MalformedResponseError(f"'{mech}' entry is not an object: {entry!r}")
        expected_keys = {"detected", "confidence", "evidence_text"}
        if set(entry) != expected_keys:
            raise MalformedResponseError(f"'{mech}' expected exactly {expected_keys}, got {set(entry)}: {entry!r}")
        detected = entry["detected"]
        if not isinstance(detected, bool):
            raise MalformedResponseError(f"'{mech}'.detected is not a boolean: {detected!r}")
        try:
            confidence = float(entry["confidence"])
        except (TypeError, ValueError) as exc:
            raise MalformedResponseError(f"'{mech}'.confidence is not a number: {entry['confidence']!r}") from exc
        if not (0.0 <= confidence <= 1.0):
            raise MalformedResponseError(f"'{mech}'.confidence {confidence} outside [0.0, 1.0]")
        evidence_text = entry["evidence_text"]
        if not isinstance(evidence_text, str) or not evidence_text.strip():
            raise MalformedResponseError(f"'{mech}'.evidence_text is empty: {evidence_text!r}")
        result[mech] = {"detected": detected, "confidence": confidence, "evidence_text": evidence_text}
    return result


class OpenRouterLLMClient:
    """Implements the LLMClient protocol via OpenRouter's OpenAI-compatible
    /chat/completions endpoint. Stateful only in that it records the last
    call's latency/token usage for the evaluation script to read — this
    extra capability is not part of the LLMClient protocol and nothing
    else in the app relies on it."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from dotenv import load_dotenv
        from openai import OpenAI  # lazy import: only required if this class is actually used

        # Populates os.environ from a .env file found in the cwd or an
        # ancestor directory (never overrides a var already set in the
        # real environment) — lazy, same as the openai import above, so
        # the mock-only/CI path never needs python-dotenv installed.
        load_dotenv()

        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.prompt_version = PROMPT_VERSION  # old exclusive-classifier prompt (classify_failure)
        self.semantic_prompt_version = SEMANTIC_PROMPT_VERSION  # current prompt (classify_semantic)
        self.last_latency_seconds: float | None = None
        self.last_input_tokens: int | None = None
        self.last_output_tokens: int | None = None
        self.last_retry_count: int = 0
        self.last_fallback: bool = False

    @property
    def model(self) -> str:
        return self._model

    def _call_once(self, context: SessionContext) -> dict:
        response = self._client.chat.completions.create(**build_chat_kwargs(self._model, context))
        usage = getattr(response, "usage", None)
        self.last_input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        self.last_output_tokens = getattr(usage, "completion_tokens", None) if usage else None

        text = response.choices[0].message.content
        return parse_and_validate(text)

    def classify_failure(self, context: SessionContext) -> FailureClassification:
        self.last_fallback = False
        last_error: Exception | None = None
        t0 = time.monotonic()
        for attempt in range(MAX_RETRIES + 1):
            self.last_retry_count = attempt
            try:
                parsed = self._call_once(context)
                self.last_latency_seconds = time.monotonic() - t0
                return FailureClassification(
                    failure_mode=parsed["failure_mode"],
                    confidence=float(parsed["confidence"]),
                    evidence_text=str(parsed["evidence_text"]),
                )
            except Exception as exc:  # malformed JSON, unknown taxonomy label, network error, etc.
                last_error = exc
                continue
        # Bounded retries exhausted: fail safe rather than raise, so one bad
        # session never aborts an evaluation run over a whole subset — but
        # record the failure so the caller can count and report it.
        self.last_latency_seconds = time.monotonic() - t0
        self.last_fallback = True
        return FailureClassification(
            failure_mode="other",
            confidence=0.0,
            evidence_text=f"classification failed after {MAX_RETRIES} retries, defaulted to 'other': {last_error}",
        )

    def classify_semantic(self, context: SessionContext) -> SemanticAttribution:
        """The one real call per session for the three semantic mechanisms.
        Unlike classify_failure, this does NOT fail safe into a disguised
        normal-looking result on exhausted retries — it raises, so the
        caller (classification_pipeline) can record the session as
        malformed/not-evaluated for these three mechanisms rather than
        silently writing an all-false prediction that looks like a real
        judgment (the exact methodological flaw the benchmark work
        surfaced in the old exclusive classifier)."""
        self.last_fallback = False
        last_error: Exception | None = None
        t0 = time.monotonic()
        for attempt in range(MAX_RETRIES + 1):
            self.last_retry_count = attempt
            try:
                response = self._client.chat.completions.create(**build_semantic_chat_kwargs(self._model, context))
                usage = getattr(response, "usage", None)
                self.last_input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
                self.last_output_tokens = getattr(usage, "completion_tokens", None) if usage else None
                parsed = parse_and_validate_semantic(response.choices[0].message.content)
                self.last_latency_seconds = time.monotonic() - t0
                results = tuple(
                    MechanismResult(
                        mechanism=mech,
                        detected=parsed[mech]["detected"],
                        confidence=parsed[mech]["confidence"],
                        evidence_text=parsed[mech]["evidence_text"],
                    )
                    for mech in SEMANTIC_MECHANISMS
                )
                return SemanticAttribution(results=results)
            except Exception as exc:  # malformed JSON, schema violation, network error, etc.
                last_error = exc
                continue
        self.last_latency_seconds = time.monotonic() - t0
        self.last_fallback = True
        raise MalformedResponseError(f"semantic classification failed after {MAX_RETRIES} retries: {last_error}")

    def summarize_finding(self, finding) -> str:
        prompt = (
            "Rewrite the following finding as one clear sentence for a product manager. "
            "Use ONLY the numbers given below verbatim — do not compute or estimate any new number.\n\n"
            f"Segment: {finding.segment_label}\n"
            f"Metric: {finding.metric_name}\n"
            f"v1 value: {finding.v1_value}\n"
            f"v2 value: {finding.v2_value}\n"
            f"p-value: {finding.p_value}\n"
            f"Excess contribution: {finding.excess_contribution}\n"
            f"Dominant associated failure mode: {finding.dominant_failure_mode}\n"
        )
        response = self._client.chat.completions.create(
            model=self._model, max_tokens=150, messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
