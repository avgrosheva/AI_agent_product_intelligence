"""The support domain's registered failure mechanisms: none (Stage 3 task
7 — a domain with no relevant automatic detector simply configures no
mechanisms, rather than inheriting commerce's six or fabricating
plausible-sounding ones with nothing behind them)."""

from __future__ import annotations

from backend.core.attribution import MechanismRegistry

SUPPORT_MECHANISMS = MechanismRegistry([])
