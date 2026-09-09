"""The support domain's registered guardrail(s) — its own choice, using
the same generic evaluate_guardrails() every domain shares.

Stage 4 (configurable guardrails): loaded from guardrails.json at import
time via backend.core.config.load_guardrail_config, rather than a
hand-written GuardrailDefinition list — proving the config-file format
for a second, real domain's guardrails."""

from __future__ import annotations

from pathlib import Path

from backend.core.config import load_guardrail_config
from backend.core.guardrails import GuardrailDefinition

_CONFIG_PATH = Path(__file__).parent / "guardrails.json"

SUPPORT_GUARDRAILS: list[GuardrailDefinition] = load_guardrail_config(_CONFIG_PATH)
