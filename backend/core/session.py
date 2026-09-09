"""Generic session/agent-interaction shape (Stage 2: domain-agnostic core).

These are structural `Protocol`s, not new dataclasses replacing anything —
`backend.llm.client.SessionContext` (the commerce domain's concrete
attribution input) already satisfies `CoreSessionContext` today, with no
change to that class, because Python's structural typing only cares that
the named attributes exist with compatible types. This documents which
part of SessionContext is genuinely domain-agnostic (transcript, action
sequence, tool calls, outcome) versus the commerce-specific fields layered
on top of it (num_constraints, requested_category, recommended_products,
...), without moving or duplicating any field.

A future second domain's own context class only needs to satisfy this
Protocol to be usable by any "core" function that type-hints against it —
it does not need to inherit from anything here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class CoreToolCall(Protocol):
    tool_name: str
    success: bool
    error_type: str


class CoreSessionContext(Protocol):
    """The domain-agnostic subset of an attribution input: what any agent
    session looks like, regardless of what the agent actually does."""

    session_id: str
    transcript: tuple[tuple[str, str], ...]  # ((sender, text), ...) ordered
    action_sequence: tuple[str, ...]  # ordered action-type labels
    tool_calls: tuple[CoreToolCall, ...]
    outcome: str


@dataclass(frozen=True)
class GenericToolCall:
    tool_name: str
    success: bool
    error_type: str


@dataclass(frozen=True)
class GenericSessionContext:
    """Concrete, ready-to-use implementation of CoreSessionContext — a
    domain with no domain-specific detector input (no product evidence, no
    equivalent) can return this directly from build_session_context()
    instead of defining its own class. A domain that DOES need extra
    fields (like commerce's SessionContext/ProductEvidence) still defines
    its own concrete class instead; this one is for the common case where
    the generic subset is all a domain's detectors need."""

    session_id: str
    transcript: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    action_sequence: tuple[str, ...] = field(default_factory=tuple)
    tool_calls: tuple[GenericToolCall, ...] = field(default_factory=tuple)
    outcome: str = ""


class CoreExperiment(Protocol):
    """Already fully generic in the current schema (backend.app.models.core
    .Experiment has no commerce-specific column) — declared here only so
    "experiment/version" appears as a named core concept, not because the
    concrete model needed any change."""

    experiment_id: str
    control_version: str
    treatment_version: str


@dataclass(frozen=True)
class GenericExperimentInfo:
    """Stage 5: what DomainAdapter.list_experiments() returns — satisfies
    CoreExperiment (Protocols allow extra attributes) plus the display
    fields a generic /experiments listing needs. Both CommerceAdapter (its
    own `experiments` table) and SupportAdapter (`ingested_experiments`,
    already storing the same fields since Stage 3) build one of these from
    their own backing table — this dataclass carries no domain data."""

    experiment_id: str
    name: str
    control_version: str
    treatment_version: str
    start_date: str | None = None
    end_date: str | None = None
