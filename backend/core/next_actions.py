"""Generic fallback next-action remediation text (Stage 4).

Used by backend.investigation.recommend.synthesize_recommendation when a
domain does not register its own next-action templates — in particular
any domain whose MechanismRegistry is empty (a finding's dominant failure
mode is then always None, since there is no automatic detector to name
one), where domain-specific remediation prose does not apply. A domain
with real registered mechanisms (e.g. commerce) supplies its own richer
templates instead (backend.domains.commerce.next_actions); this generic
pair is what "domain-provided OR generic" (Stage 4 task 1) falls back to.
"""

from __future__ import annotations

GENERIC_NEXT_ACTION_TEMPLATES: dict[str, str] = {
    "other": "Manually review a sample of sessions in the affected segment to characterize the regression before further rollout.",
    "none": "Manually review a sample of sessions in the affected segment; no automatic failure-mode detector is registered for this domain.",
}
