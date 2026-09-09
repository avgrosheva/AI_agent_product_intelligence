"""Stage 11 task 3: the evidence layer for a release decision. Everything
here comes from data already computed and stored — a persisted
ReleaseEvaluation's own `breached_guardrails`/`top_findings` (including
each finding's `representative_session_ids`, Stage 11 task 4) and live
reads from the SAME DomainAdapter the evaluation itself was computed
from (session transcripts via build_session_context, and detected
mechanism instances via list_reviewable_attributions, Stage 6). Nothing
here is inferred, summarized by a model, or fabricated — a session that
can't be re-read (already deleted, or blocked by tenancy) is simply
skipped, never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.adapter import DomainAdapter
from backend.release.service import ReleaseEvaluationResult

MAX_REPRESENTATIVE_SESSIONS = 10


@dataclass(frozen=True)
class SessionEvidence:
    session_id: str
    segment_label: str
    outcome: str
    transcript_excerpt: list[tuple[str, str]]
    action_sequence: list[str]


@dataclass(frozen=True)
class NegativeSegmentEvidence:
    segment_label: str
    dimensions: tuple[str, ...]
    p_value: float | None
    excess_contribution: float | None
    dominant_failure_mode: str | None
    representative_session_ids: list[str]


@dataclass(frozen=True)
class LinkedMechanism:
    session_id: str
    failure_mode: str
    detector_source: str
    confidence: float | None
    evidence_text: str | None


@dataclass(frozen=True)
class ReleaseEvidence:
    evaluation_id: str
    domain: str
    experiment_id: str
    status: str
    breached_guardrails: list[dict] = field(default_factory=list)
    significant_negative_segments: list[NegativeSegmentEvidence] = field(default_factory=list)
    representative_sessions: list[SessionEvidence] = field(default_factory=list)
    linked_failure_mechanisms: list[LinkedMechanism] = field(default_factory=list)


def build_release_evidence(adapter: DomainAdapter, evaluation: ReleaseEvaluationResult) -> ReleaseEvidence:
    negative_segments = [
        NegativeSegmentEvidence(
            segment_label=f["segment_label"],
            dimensions=tuple(f.get("dimensions") or ()),
            p_value=f.get("p_value"),
            excess_contribution=f.get("excess_contribution"),
            dominant_failure_mode=f.get("dominant_failure_mode"),
            representative_session_ids=list(f.get("representative_session_ids") or []),
        )
        for f in evaluation.top_findings
        if (f.get("excess_contribution") or 0) < 0
    ]

    segment_by_session: dict[str, str] = {}
    ordered_session_ids: list[str] = []
    for seg in negative_segments:
        for sid in seg.representative_session_ids:
            segment_by_session.setdefault(sid, seg.segment_label)
            if sid not in ordered_session_ids:
                ordered_session_ids.append(sid)
    ordered_session_ids = ordered_session_ids[:MAX_REPRESENTATIVE_SESSIONS]

    sessions: list[SessionEvidence] = []
    for sid in ordered_session_ids:
        try:
            ctx = adapter.build_session_context(sid)
        except KeyError:
            # A representative session that no longer exists (or belongs
            # to a different project) is skipped, never fabricated.
            continue
        sessions.append(
            SessionEvidence(
                session_id=sid,
                segment_label=segment_by_session.get(sid, ""),
                outcome=ctx.outcome,
                transcript_excerpt=list(ctx.transcript)[:10],
                action_sequence=list(ctx.action_sequence),
            )
        )

    try:
        reviewable = adapter.list_reviewable_attributions(experiment_id=evaluation.experiment_id)
    except Exception:
        reviewable = []
    linked = [
        LinkedMechanism(
            session_id=r.session_id,
            failure_mode=r.failure_mode,
            detector_source=r.detector_source,
            confidence=r.confidence,
            evidence_text=r.evidence_text,
        )
        for r in reviewable
        if r.session_id in ordered_session_ids
    ]

    return ReleaseEvidence(
        evaluation_id=evaluation.evaluation_id,
        domain=evaluation.domain,
        experiment_id=evaluation.experiment_id,
        status=evaluation.status,
        breached_guardrails=evaluation.breached_guardrails,
        significant_negative_segments=negative_segments,
        representative_sessions=sessions,
        linked_failure_mechanisms=linked,
    )
