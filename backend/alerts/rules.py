"""Stage 6 task 1: deterministic alert rules over an already-persisted
release evaluation's fields (backend.release.service._investigation_to_
release_fields' output plus the resulting status). Pure functions of
already-computed numbers — same "no LLM/no randomness in the decision"
discipline as backend.investigation.recommend.synthesize_recommendation.

Each candidate alert carries a `dedup_key` — backend.alerts.service uses
it to skip creating a new row when an OPEN alert with the same
(domain, experiment_id, rule, dedup_key) already exists (task 7:
"alert creation/deduplication").
"""

from __future__ import annotations

from dataclasses import dataclass


def _humanize(name: str) -> str:
    """Renders an internal snake_case metric/guardrail/segment identifier
    as a plain phrase (e.g. "p95_latency" -> "p95 latency") for the one
    place these names are read as prose rather than shown as a label next
    to a value -- mirrors backend.release.summary._humanize, which does
    the same job for the release-decision explanation sentence."""
    return name.replace("_", " ")


@dataclass(frozen=True)
class CandidateAlert:
    rule: str
    severity: str
    reason: str
    related_guardrail: str | None
    related_finding: str | None
    dedup_key: str


def evaluate_alert_rules(status: str, fields: dict, primary_metric: str) -> list[CandidateAlert]:
    """`status` is one of "SHIP"/"HOLD"/"ROLLBACK" (backend.release.service.
    STATUS_BY_VERDICT); `fields` is the dict evaluate_release() returns
    (key_metrics, breached_guardrails, top_findings, has_negative_segment).
    """
    alerts: list[CandidateAlert] = []

    if status == "ROLLBACK":
        alerts.append(
            CandidateAlert(
                rule="rollback",
                severity="critical",
                reason=f"'{_humanize(primary_metric)}' is significantly worse in v2 (roll_back verdict) — release should be rolled back.",
                related_guardrail=None,
                related_finding=None,
                dedup_key="rollback",
            )
        )

    for guardrail in fields.get("breached_guardrails", []):
        if guardrail.get("severity") != "blocking":
            continue
        alerts.append(
            CandidateAlert(
                rule="blocking_guardrail_breach",
                severity="critical",
                reason=f"Blocking guardrail '{_humanize(guardrail['name'])}' breached ({guardrail['threshold_description']}): v1={guardrail['v1_value']}, v2={guardrail['v2_value']}.",
                related_guardrail=guardrail["name"],
                related_finding=None,
                dedup_key=f"guardrail:{guardrail['name']}",
            )
        )

    if status == "HOLD" and fields.get("has_negative_segment"):
        findings = fields.get("top_findings", [])
        negative = [f for f in findings if f.get("excess_contribution") is not None and f["excess_contribution"] < 0]
        top_negative = min(negative, key=lambda f: f["excess_contribution"], default=None) if negative else None
        related_finding = top_negative["segment_label"] if top_negative else None
        alerts.append(
            CandidateAlert(
                rule="hold_negative_segment",
                severity="warning",
                reason=(
                    f"Hold verdict with a significant negative segment"
                    + (f": '{_humanize(related_finding)}'." if related_finding else ".")
                ),
                related_guardrail=None,
                related_finding=related_finding,
                dedup_key=f"negative_segment:{related_finding or 'unknown'}",
            )
        )

    return alerts
