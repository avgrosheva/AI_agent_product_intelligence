"""Generic failure-attribution registry (Stage 2: domain-agnostic core).

A `Mechanism` is just a name, a source ("deterministic" — recoverable from
structured telemetry alone — or "semantic" — requires interpreting
conversation context), and a description. A `MechanismRegistry` is an
ordered collection of these. Neither type knows or cares what the
mechanisms actually are; that vocabulary is domain data, supplied by
whichever domain module builds a registry (see
backend/domains/commerce/mechanisms.py for the current shopping-agent's
six mechanisms).

This does not replace backend.llm.client.MechanismResult/SemanticAttribution
(the concrete attribution result types the pipeline actually produces) —
those stay exactly as they are, still validated against the commerce
domain's registered mechanism names, so nothing about current behavior
changes. This module is the generic pattern the commerce registry is now
built from, so a second domain could register its own mechanisms the same
way without touching this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

MechanismSource = Literal["deterministic", "semantic"]


@dataclass(frozen=True)
class ReviewableAttribution:
    """Stage 6: one detected (detected=true) mechanism instance a human
    analyst could review — DomainAdapter.list_reviewable_attributions()'s
    element type. A domain with no attribution storage of its own (support
    — Stage 3 task 7: zero registered mechanisms) simply returns an empty
    list; nothing downstream (the review queue, session-detail review
    fields) special-cases that, it's just an empty result."""

    session_id: str
    experiment_id: str
    agent_version: str
    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None


@dataclass(frozen=True)
class Mechanism:
    name: str
    source: MechanismSource
    description: str = ""


class MechanismRegistry:
    """Ordered collection of Mechanisms. Order is preserved (and matters:
    downstream validation of a multi-label result vector checks the
    semantic mechanisms' names against `.semantic` in registration order)."""

    def __init__(self, mechanisms: Sequence[Mechanism]):
        names = [m.name for m in mechanisms]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate mechanism names: {names}")
        self._mechanisms: tuple[Mechanism, ...] = tuple(mechanisms)

    @property
    def mechanisms(self) -> tuple[Mechanism, ...]:
        return self._mechanisms

    @property
    def deterministic(self) -> tuple[str, ...]:
        return tuple(m.name for m in self._mechanisms if m.source == "deterministic")

    @property
    def semantic(self) -> tuple[str, ...]:
        return tuple(m.name for m in self._mechanisms if m.source == "semantic")

    @property
    def all_names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self._mechanisms)

    def __contains__(self, name: str) -> bool:
        return name in self.all_names

    def __iter__(self):
        return iter(self._mechanisms)
