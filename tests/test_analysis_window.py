"""Stage 13 tasks 1-3/9: the AnalysisWindow value object itself, and
proof that both DomainAdapter implementations (support, commerce) apply
the exact same inclusive-both-ends rule — started_at >= start AND
started_at <= end — to analytics_base_df and agent_actions_df."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from backend.core.analysis_window import AnalysisWindow

# -- pure AnalysisWindow behavior -----------------------------------------


def test_window_rejects_start_after_end():
    end = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError):
        AnalysisWindow(start=end + timedelta(hours=1), end=end)


def test_window_contains_is_inclusive_both_ends():
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 1, 6, 0, 0)
    window = AnalysisWindow(start=start, end=end)
    assert window.contains(start) is True
    assert window.contains(end) is True
    assert window.contains(start + timedelta(hours=3)) is True
    assert window.contains(start - timedelta(microseconds=1)) is False
    assert window.contains(end + timedelta(microseconds=1)) is False


# -- support adapter: exact boundary behavior ------------------------------


def _ingest_boundary_sessions(api_client, project_id: str, tag: str, window_start: datetime, window_end: datetime) -> None:
    def session(sid: str, started_at: datetime) -> dict:
        return {
            "external_session_id": sid, "external_experiment_id": f"win-exp-{tag}", "agent_version": "v1",
            "external_user_id": f"user-{sid}", "started_at": started_at.isoformat(), "outcome": {"label": "resolved", "metrics": []},
            "actions": [{"external_action_id": f"{sid}-a0", "sequence_index": 0, "action_type": "triage_ticket", "started_at": started_at.isoformat(), "tool_calls": []}],
        }

    sessions = [
        session(f"win-{tag}-before", window_start - timedelta(hours=1)),
        session(f"win-{tag}-at-start", window_start),
        session(f"win-{tag}-inside", window_start + timedelta(hours=1)),
        session(f"win-{tag}-at-end", window_end),
        session(f"win-{tag}-after", window_end + timedelta(hours=1)),
    ]
    payload = {"domain": "support", "experiments": [{"external_experiment_id": f"win-exp-{tag}", "name": f"Window Boundary Test {tag}", "control_version": "v1", "treatment_version": "v2"}], "sessions": sessions}
    resp = api_client.post("/api/v1/ingest/sessions", json=payload, params={"project_id": project_id})
    assert resp.status_code == 201


def test_support_adapter_windowed_session_count_is_exactly_three_of_five(api_client, support_project_id):
    from backend.domains.support.adapter import SupportAdapter
    from backend.app.db import get_database_url
    from sqlalchemy import create_engine, text

    tag = f"boundcount-{uuid.uuid4().hex[:8]}"
    window_start = datetime(2027, 1, 1, 0, 0, 0)
    window_end = datetime(2027, 1, 1, 6, 0, 0)
    _ingest_boundary_sessions(api_client, support_project_id, tag, window_start, window_end)

    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        exp_id = conn.execute(text("SELECT experiment_id FROM ingested_experiments WHERE external_experiment_id = :e AND project_id = :p"), {"e": f"win-exp-{tag}", "p": support_project_id}).scalar_one()

    adapter = SupportAdapter(engine, project_id=support_project_id)
    window = AnalysisWindow(start=window_start, end=window_end)

    unwindowed = adapter.analytics_base_df(experiment_id=str(exp_id))
    windowed = adapter.analytics_base_df(experiment_id=str(exp_id), window=window)

    assert len(unwindowed) == 5
    assert len(windowed) == 3  # at-start, inside, at-end -- before/after excluded


def test_support_adapter_agent_actions_df_is_windowed_too(api_client, support_project_id):
    from backend.domains.support.adapter import SupportAdapter
    from backend.app.db import get_database_url
    from sqlalchemy import create_engine, text

    tag = f"boundactions-{uuid.uuid4().hex[:8]}"
    window_start = datetime(2027, 2, 1, 0, 0, 0)
    window_end = datetime(2027, 2, 1, 6, 0, 0)
    _ingest_boundary_sessions(api_client, support_project_id, tag, window_start, window_end)

    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        exp_id = conn.execute(text("SELECT experiment_id FROM ingested_experiments WHERE external_experiment_id = :e AND project_id = :p"), {"e": f"win-exp-{tag}", "p": support_project_id}).scalar_one()

    adapter = SupportAdapter(engine, project_id=support_project_id)
    window = AnalysisWindow(start=window_start, end=window_end)

    unwindowed_actions = adapter.agent_actions_df(experiment_id=str(exp_id))
    windowed_actions = adapter.agent_actions_df(experiment_id=str(exp_id), window=window)

    assert len(unwindowed_actions) == 5  # one action per session
    assert len(windowed_actions) == 3


def test_no_window_means_full_dataset_unchanged(api_client, support_project_id):
    """Stage 13 task 4: omitting `window` (None, the default) must be
    identical to calling without the parameter at all."""
    from backend.domains.support.adapter import SupportAdapter
    from backend.app.db import get_database_url
    from sqlalchemy import create_engine

    engine = create_engine(get_database_url())
    adapter = SupportAdapter(engine, project_id=support_project_id)
    a = adapter.analytics_base_df()
    b = adapter.analytics_base_df(window=None)
    assert len(a) == len(b)
