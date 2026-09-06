"""Real LLM classifier (AI_EVALUATION.md SS3). Requires ANTHROPIC_API_KEY
and the optional `anthropic` package (`pip install -e ".[llm]"`) — neither
is imported by anything else in the codebase, so the test suite and the
RuleBasedMockClient path never depend on this module or on live API
availability (Stage 2 review requirement #10).

This is a separate, reproducible demo/evaluation path: run
`python -m scripts.run_classification --client anthropic` with a real key
configured to populate failure_labels via this client instead of the mock.
"""

from __future__ import annotations

import json
import os

from backend.llm.client import FailureClassification, SessionContext
from backend.llm.prompts.failure_classification import SYSTEM_PROMPT, render_user_message

MODEL_NAME = "claude-sonnet-5"
MAX_RETRIES = 1


class AnthropicLLMClient:
    """Implements the LLMClient protocol via the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None, model: str = MODEL_NAME):
        import anthropic  # lazy import: only required if this class is actually used

        self._client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self._model = model

    def _call(self, context: SessionContext) -> dict:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": render_user_message(context)}],
        )
        text = response.content[0].text
        return json.loads(text)

    def classify_failure(self, context: SessionContext) -> FailureClassification:
        last_error = None
        for _ in range(MAX_RETRIES + 1):
            try:
                parsed = self._call(context)
                return FailureClassification(
                    failure_mode=parsed["failure_mode"],
                    confidence=float(parsed["confidence"]),
                    evidence_text=str(parsed["evidence_text"]),
                )
            except Exception as exc:  # malformed JSON, unknown label, network error, etc.
                last_error = exc
                continue
        return FailureClassification(
            failure_mode="other",
            confidence=0.0,
            evidence_text=f"classification failed after retry, defaulted to 'other': {last_error}",
        )

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
        response = self._client.messages.create(
            model=self._model, max_tokens=150, messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
