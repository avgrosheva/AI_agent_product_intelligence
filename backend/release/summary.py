"""Stage 14: a single, UI-optimized view of one release evaluation — the
release-summary endpoint's only data source. Every field here is either
already stored on the ReleaseEvaluation row, already computed by
backend.release.evidence.build_release_evidence (Stage 11), or a plain,
deterministic derivation from those two (a percentage-point delta, a
p-value bucket, a templated sentence) — no new statistics, no new
decision logic, and nothing generated beyond what the stored facts
support (task 2: "do not generate unsupported explanations").

Same stored evaluation -> same explanation text and the same evidence
order, every time (task 7): every derivation here is a pure function of
already-persisted fields, and every list is explicitly sorted rather
than left in incidental dict/query order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from backend.core.adapter import DomainAdapter
from backend.core.next_actions import GENERIC_NEXT_ACTION_TEMPLATES
from backend.release.evidence import ReleaseEvidence, build_release_evidence
from backend.release.service import ReleaseEvaluationResult
from backend.review.service import get_reviews_for_session


@dataclass(frozen=True)
class DecisionSummary:
    evaluation_id: str
    domain: str
    experiment_id: str
    primary_metric: str
    verdict: str
    raw_verdict: str
    primary_reason: str
    primary_metric_v1: float | None
    primary_metric_v2: float | None
    primary_metric_delta: float | None
    primary_metric_p_value: float | None
    breached_guardrails: list[dict]
    significant_negative_segment_count: int
    data_quality_status: str
    data_quality_gated: bool
    economics_impact: float | None
    confidence: str  # strong | moderate | weak | insufficient_evidence


@dataclass(frozen=True)
class EvidenceItem:
    rank: int
    category: str  # blocking_guardrail | primary_metric | negative_segment | economics | failure_mechanism | representative_session
    summary: str


@dataclass(frozen=True)
class FindingExplanation:
    segment_label: str
    dimensions: tuple[str, ...]
    metric: str
    v1_value: float | None
    v2_value: float | None
    delta: float | None
    p_value: float | None
    excess_contribution: float | None
    dominant_failure_mode: str | None
    representative_session_ids: list[str]
    next_action: str


@dataclass(frozen=True)
class SessionEvidenceDetail:
    session_id: str
    segment_label: str
    outcome: str
    transcript_excerpt: list[tuple[str, str]]
    action_sequence: list[str]
    detected_mechanisms: list[str]
    human_review_status: str  # reviewed | not_reviewed
    selected_because: str


@dataclass(frozen=True)
class MonitoringWindowInfo:
    data_window_start: object | None
    data_window_end: object | None
    window_hours: int | None


@dataclass(frozen=True)
class ReleaseSummary:
    decision: DecisionSummary
    explanation_text: str
    evidence_hierarchy: list[EvidenceItem]
    findings: list[FindingExplanation]
    representative_sessions: list[SessionEvidenceDetail]
    economics: dict | None
    data_quality_status: str
    monitoring_window: MonitoringWindowInfo


def _confidence_from_p_value(p_value: float | None) -> str:
    if p_value is None:
        return "insufficient_evidence"
    if p_value < 0.01:
        return "strong"
    if p_value < 0.05:
        return "moderate"
    return "weak"


def _pct_point(value: float | None) -> str:
    return f"{abs(value) * 100:.1f}pp" if value is not None else "an unmeasured amount"


def generate_explanation_text(decision: DecisionSummary) -> str:
    """Task 6: a short, deterministic sentence built only from already-
    computed fields — e.g. "ROLLBACK because resolution_rate decreased
    by 60.0pp and escalation_rate_guardrail breached its blocking
    guardrail." No LLM involved; this is the ONLY explanation the API
    ever returns unless a caller explicitly asks for an optional
    secondary LLM gloss (not implemented here — task 6 allows but does
    not require one, and none of the structured fields may ever be
    replaced by it)."""
    delta = decision.primary_metric_delta
    if delta is None:
        change_clause = f"{decision.primary_metric} could not be measured"
    elif delta > 0:
        change_clause = f"{decision.primary_metric} increased by {_pct_point(delta)}"
    elif delta < 0:
        change_clause = f"{decision.primary_metric} decreased by {_pct_point(delta)}"
    else:
        change_clause = f"{decision.primary_metric} was unchanged"

    clauses = [change_clause]

    blocking_names = [g["name"] for g in decision.breached_guardrails if g.get("severity") == "blocking"]
    if blocking_names:
        joined = " and ".join(blocking_names)
        clauses.append(f"{joined} breached its blocking guardrail" if len(blocking_names) == 1 else f"{joined} breached their blocking guardrails")

    if decision.verdict == "HOLD" and not blocking_names and decision.significant_negative_segment_count > 0:
        clauses.append(f"{decision.significant_negative_segment_count} significant negative segment(s) were found")

    if decision.data_quality_gated:
        clauses.append("project data quality is critical, so a confident SHIP is withheld")

    return f"{decision.verdict} because " + " and ".join(clauses) + "."


def _build_evidence_hierarchy(decision: DecisionSummary, evidence: ReleaseEvidence) -> list[EvidenceItem]:
    """Task 2's fixed priority order: blocking guardrails, primary metric
    change, significant negative segments, economics impact, detected
    failure mechanisms, representative sessions. Each category is
    entirely skipped when it has nothing to report — never a placeholder
    item."""
    items: list[tuple[str, str]] = []

    for g in decision.breached_guardrails:
        if g.get("severity") == "blocking":
            items.append(("blocking_guardrail", f"Blocking guardrail '{g['name']}' breached ({g.get('threshold_description', 'threshold exceeded')}): v1={g.get('v1_value')}, v2={g.get('v2_value')}."))

    delta = decision.primary_metric_delta
    if delta is not None:
        direction = "improved" if delta > 0 else "regressed" if delta < 0 else "was unchanged"
        p_text = f"p={decision.primary_metric_p_value:.2e}" if decision.primary_metric_p_value is not None else "p=n/a"
        items.append(("primary_metric", f"Primary metric '{decision.primary_metric}' {direction} by {_pct_point(delta)} ({p_text})."))

    for seg in evidence.significant_negative_segments:
        p_text = f"p={seg.p_value:.2e}" if seg.p_value is not None else "p=n/a"
        items.append(("negative_segment", f"Segment '{seg.segment_label}' shows a negative excess contribution of {seg.excess_contribution:.4f} ({p_text})."))

    if decision.economics_impact is not None:
        direction = "positive" if decision.economics_impact > 0 else "negative" if decision.economics_impact < 0 else "neutral"
        items.append(("economics", f"Estimated business impact per session is {decision.economics_impact:.4f} ({direction})."))

    seen_modes: list[str] = []
    for seg in evidence.significant_negative_segments:
        if seg.dominant_failure_mode and seg.dominant_failure_mode not in seen_modes:
            seen_modes.append(seg.dominant_failure_mode)
            items.append(("failure_mechanism", f"Failure mechanism '{seg.dominant_failure_mode}' detected as the dominant contributor in segment '{seg.segment_label}'."))

    if evidence.representative_sessions:
        items.append(("representative_session", f"{len(evidence.representative_sessions)} representative session(s) selected across {len(evidence.significant_negative_segments)} segment(s) for detailed review."))

    return [EvidenceItem(rank=i + 1, category=category, summary=summary) for i, (category, summary) in enumerate(items)]


def _selection_reason(dominant_failure_mode: str | None) -> str:
    if dominant_failure_mode:
        return f"Sampled from the treatment arm, preferring sessions where the detected failure mechanism '{dominant_failure_mode}' was present."
    return "Sampled from the treatment arm, preferring sessions with this domain's own negative outcome value."


def _next_action_for(adapter: DomainAdapter, dominant_failure_mode: str | None) -> str:
    templates = adapter.next_action_templates() or GENERIC_NEXT_ACTION_TEMPLATES
    key = dominant_failure_mode or "none"
    return templates.get(key, templates.get("other", GENERIC_NEXT_ACTION_TEMPLATES["other"]))


def build_release_summary(engine: Engine, adapter: DomainAdapter, evaluation: ReleaseEvaluationResult) -> ReleaseSummary:
    primary = evaluation.key_metrics.get(evaluation.primary_metric, {})
    v1 = primary.get("v1")
    v2 = primary.get("v2")
    delta = (v2 - v1) if (v1 is not None and v2 is not None) else None
    p_value = primary.get("p_value")

    negative_segments = [f for f in evaluation.top_findings if (f.get("excess_contribution") or 0) < 0]

    decision = DecisionSummary(
        evaluation_id=evaluation.evaluation_id,
        domain=evaluation.domain,
        experiment_id=evaluation.experiment_id,
        primary_metric=evaluation.primary_metric,
        verdict=evaluation.status,
        raw_verdict=evaluation.raw_status,
        primary_reason=evaluation.primary_reason,
        primary_metric_v1=v1,
        primary_metric_v2=v2,
        primary_metric_delta=delta,
        primary_metric_p_value=p_value,
        breached_guardrails=evaluation.breached_guardrails,
        significant_negative_segment_count=len(negative_segments),
        data_quality_status=evaluation.data_quality_status,
        data_quality_gated=evaluation.data_quality_gated,
        economics_impact=(evaluation.economics or {}).get("estimated_business_impact_per_session"),
        confidence=_confidence_from_p_value(p_value),
    )

    evidence = build_release_evidence(adapter, evaluation)
    explanation_text = generate_explanation_text(decision)
    evidence_hierarchy = _build_evidence_hierarchy(decision, evidence)

    # Task 3: every significant finding, deterministically ordered (most
    # negative excess contribution first — the same order the Investigation
    # engine itself ranks findings in, tie-broken by segment_label for
    # full determinism when two findings tie exactly).
    ordered_findings = sorted(evaluation.top_findings, key=lambda f: (f.get("excess_contribution") or 0.0, f.get("segment_label", "")))
    findings = [
        FindingExplanation(
            segment_label=f["segment_label"],
            dimensions=tuple(f.get("dimensions") or ()),
            metric=evaluation.primary_metric,
            v1_value=f.get("cluster_mean_v1"),
            v2_value=f.get("cluster_mean_v2"),
            delta=(f["cluster_mean_v2"] - f["cluster_mean_v1"]) if (f.get("cluster_mean_v1") is not None and f.get("cluster_mean_v2") is not None) else None,
            p_value=f.get("p_value"),
            excess_contribution=f.get("excess_contribution"),
            dominant_failure_mode=f.get("dominant_failure_mode"),
            representative_session_ids=list(f.get("representative_session_ids") or []),
            next_action=_next_action_for(adapter, f.get("dominant_failure_mode")),
        )
        for f in ordered_findings
    ]

    mechanisms_by_session: dict[str, list[str]] = {}
    for m in evidence.linked_failure_mechanisms:
        mechanisms_by_session.setdefault(m.session_id, []).append(m.failure_mode)

    finding_mode_by_session: dict[str, str | None] = {}
    for seg in evidence.significant_negative_segments:
        for sid in seg.representative_session_ids:
            finding_mode_by_session.setdefault(sid, seg.dominant_failure_mode)

    representative_sessions = [
        SessionEvidenceDetail(
            session_id=s.session_id,
            segment_label=s.segment_label,
            outcome=s.outcome,
            transcript_excerpt=s.transcript_excerpt,
            action_sequence=s.action_sequence,
            detected_mechanisms=mechanisms_by_session.get(s.session_id, []),
            human_review_status=_human_review_status(engine, evaluation, s.session_id),
            selected_because=_selection_reason(finding_mode_by_session.get(s.session_id)),
        )
        for s in evidence.representative_sessions
    ]

    return ReleaseSummary(
        decision=decision,
        explanation_text=explanation_text,
        evidence_hierarchy=evidence_hierarchy,
        findings=findings,
        representative_sessions=representative_sessions,
        economics=evaluation.economics,
        data_quality_status=evaluation.data_quality_status,
        monitoring_window=MonitoringWindowInfo(
            data_window_start=evaluation.data_window_start, data_window_end=evaluation.data_window_end, window_hours=evaluation.window_hours
        ),
    )


def _human_review_status(engine: Engine, evaluation: ReleaseEvaluationResult, session_id: str) -> str:
    reviews = get_reviews_for_session(engine, evaluation.domain, session_id, project_id=evaluation.project_id)
    return "reviewed" if reviews else "not_reviewed"
