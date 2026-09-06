"""Session list/filter and full detail reconstruction.

Filters accepted here are deliberately the same vocabulary Investigation's
SegmentFilter uses (backend.investigation.segments' registered pre-treatment
dimensions), so a finding's segment_filter can be passed straight through
to reproduce exactly the sessions behind it, plus outcome/agent_version/
failure_mode for drilling into a specific finding's failure mode.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from backend.app.dependencies import get_base_df, get_engine
from backend.app.schemas.common import ClassifierProvenance
from backend.app.schemas.sessions import (
    AgentActionSchema,
    EvaluationSchema,
    FailureClassificationSchema,
    MessageSchema,
    ProductEventSchema,
    RecommendationItemSchema,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummary,
    ToolCallSchema,
)
from backend.llm.provenance import get_evaluation_status, read_classifier_metadata

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    experiment_id: str | None = None,
    agent_version: str | None = None,
    requested_category: str | None = None,
    constraint_count_bucket: str | None = None,
    platform: str | None = None,
    device_tier: str | None = None,
    locale: str | None = None,
    persona: str | None = None,
    outcome: str | None = None,
    failure_mode: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    df = get_base_df(experiment_id=experiment_id)

    filters_applied: dict[str, str] = {}
    for col, value in [
        ("agent_version", agent_version), ("requested_category", requested_category),
        ("constraint_count_bucket", constraint_count_bucket), ("platform", platform),
        ("device_tier", device_tier), ("locale", locale), ("persona", persona), ("outcome", outcome),
    ]:
        if value is not None:
            df = df[df[col] == value]
            filters_applied[col] = value

    if failure_mode is not None:
        with get_engine().connect() as conn:
            labeled = conn.execute(
                text("SELECT session_id FROM failure_labels WHERE failure_mode = :fm"), {"fm": failure_mode}
            ).scalars().all()
        labeled_ids = {str(x) for x in labeled}
        df = df[df["session_id"].astype(str).isin(labeled_ids)]
        filters_applied["failure_mode"] = failure_mode

    total = len(df)
    page = df.sort_values("started_at", ascending=False).iloc[offset : offset + limit]

    failure_by_session = {}
    if len(page):
        with get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT session_id, failure_mode::text AS failure_mode FROM failure_labels WHERE session_id = ANY(:ids)"),
                {"ids": [uuid.UUID(str(x)) for x in page["session_id"]]},
            ).mappings().all()
        failure_by_session = {str(r["session_id"]): r["failure_mode"] for r in rows}

    items = [
        SessionSummary(
            session_id=str(row.session_id),
            agent_version=row.agent_version,
            requested_category=row.requested_category,
            constraint_count_bucket=row.constraint_count_bucket,
            platform=row.platform,
            device_tier=row.device_tier,
            locale=row.locale,
            persona=row.persona,
            outcome=row.outcome,
            num_turns=row.num_turns,
            total_latency_ms=row.total_latency_ms,
            total_cost_usd=row.total_cost_usd,
            started_at=row.started_at,
            failure_mode=failure_by_session.get(str(row.session_id)),
        )
        for row in page.itertuples()
    ]
    return SessionListResponse(items=items, total=total, limit=limit, offset=offset, filters_applied=filters_applied)


def _classifier_provenance() -> ClassifierProvenance:
    meta = read_classifier_metadata()
    status = get_evaluation_status()
    if meta is None:
        return ClassifierProvenance(classifier_type="not_classified", is_mock=False, evaluation_status=status)
    return ClassifierProvenance(
        classifier_type=meta.classifier_type, classifier_version=meta.classifier_version,
        is_mock=meta.is_mock, evaluation_status=status, run_at=meta.run_at,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(session_id: str) -> SessionDetailResponse:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"'{session_id}' is not a valid session id")

    with get_engine().connect() as conn:
        session_row = conn.execute(
            text(
                """
                SELECT s.session_id, s.agent_version::text AS agent_version, s.requested_category::text AS requested_category,
                       CASE WHEN s.num_constraints <= 1 THEN '0-1' WHEN s.num_constraints = 2 THEN '2' ELSE '3+' END AS constraint_count_bucket,
                       s.platform::text AS platform, s.device_tier::text AS device_tier, s.locale::text AS locale,
                       u.persona::text AS persona, s.num_constraints, s.outcome::text AS outcome, s.num_turns,
                       s.total_latency_ms, s.total_tokens_in, s.total_tokens_out, s.total_cost_usd::float8 AS total_cost_usd,
                       s.started_at, s.ended_at
                FROM sessions s JOIN users u ON u.user_id = s.user_id
                WHERE s.session_id = :sid
                """
            ),
            {"sid": sid},
        ).mappings().first()

        if session_row is None:
            raise HTTPException(status_code=404, detail=f"No session with id '{session_id}'")

        messages = conn.execute(
            # ORDER BY sender (alphabetical) would sort "agent" before "user"
            # within the same turn_index, scrambling chronological order —
            # created_at is the actual chronological key. Stage 6: exposed
            # in the response too (not just used for ORDER BY) so the
            # frontend can build one true merged timeline across messages/
            # actions/tool_calls/product_events instead of guessing an
            # interleave from turn_index/sequence_index alone, which are
            # not comparable across those different event types.
            text("SELECT turn_index, sender::text AS sender, text, tokens, latency_ms, created_at FROM messages WHERE session_id = :sid ORDER BY created_at"),
            {"sid": sid},
        ).mappings().all()
        actions = conn.execute(
            text("SELECT sequence_index, action_type::text AS action_type, latency_ms, model_name, started_at FROM agent_actions WHERE session_id = :sid ORDER BY sequence_index"),
            {"sid": sid},
        ).mappings().all()
        tool_calls = conn.execute(
            text(
                """
                SELECT tc.tool_name::text AS tool_name, tc.success, tc.error_type::text AS error_type, tc.latency_ms,
                       a.sequence_index AS action_sequence_index, a.started_at AS action_started_at
                FROM tool_calls tc JOIN agent_actions a ON a.action_id = tc.action_id
                WHERE tc.session_id = :sid ORDER BY a.sequence_index
                """
            ),
            {"sid": sid},
        ).mappings().all()
        recs = conn.execute(
            text("SELECT product_id, rank_position, clicked, satisfies_constraints FROM recommendations WHERE session_id = :sid ORDER BY rank_position"),
            {"sid": sid},
        ).mappings().all()
        events = conn.execute(
            text("SELECT event_type::text AS event_type, event_time, price_at_event FROM product_events WHERE session_id = :sid ORDER BY event_time"),
            {"sid": sid},
        ).mappings().all()
        evaluations = conn.execute(
            text("SELECT eval_type::text AS eval_type, score, evaluator::text AS evaluator FROM evaluations WHERE session_id = :sid"),
            {"sid": sid},
        ).mappings().all()
        failure_label = conn.execute(
            text("SELECT failure_mode::text AS failure_mode, confidence, evidence_text, source::text AS source FROM failure_labels WHERE session_id = :sid"),
            {"sid": sid},
        ).mappings().first()

    provenance = _classifier_provenance()
    failure_classification = (
        FailureClassificationSchema(
            failure_mode=failure_label["failure_mode"], confidence=failure_label["confidence"],
            evidence_text=failure_label["evidence_text"], source=failure_label["source"], provenance=provenance,
        )
        if failure_label is not None
        else None
    )

    return SessionDetailResponse(
        session_id=str(session_row["session_id"]),
        agent_version=session_row["agent_version"],
        requested_category=session_row["requested_category"],
        constraint_count_bucket=session_row["constraint_count_bucket"],
        platform=session_row["platform"],
        device_tier=session_row["device_tier"],
        locale=session_row["locale"],
        persona=session_row["persona"],
        num_constraints=session_row["num_constraints"],
        outcome=session_row["outcome"],
        num_turns=session_row["num_turns"],
        total_latency_ms=session_row["total_latency_ms"],
        total_tokens_in=session_row["total_tokens_in"],
        total_tokens_out=session_row["total_tokens_out"],
        total_cost_usd=session_row["total_cost_usd"],
        started_at=session_row["started_at"],
        ended_at=session_row["ended_at"],
        transcript=[MessageSchema(**dict(m)) for m in messages],
        agent_actions=[AgentActionSchema(**dict(a)) for a in actions],
        tool_calls=[ToolCallSchema(**dict(t)) for t in tool_calls],
        recommendations=[
            RecommendationItemSchema(
                product_id=str(r["product_id"]), rank_position=r["rank_position"],
                clicked=r["clicked"], satisfies_constraints=r["satisfies_constraints"],
            )
            for r in recs
        ],
        product_events=[ProductEventSchema(**dict(e)) for e in events],
        evaluations=[EvaluationSchema(**dict(e)) for e in evaluations],
        failure_classification=failure_classification,
    )
