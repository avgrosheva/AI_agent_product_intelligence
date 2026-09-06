"""User-level experiment assignment stability and treatment balance
(DATA_MODEL.md SS1, SS3.4; STATISTICS.md SS2)."""

from __future__ import annotations

from sqlalchemy import text


def test_every_user_has_a_single_agent_version_per_experiment(db_engine):
    """The user, not the session, is the randomization unit: a user's
    sessions within one experiment must never mix v1 and v2."""
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT user_id, experiment_id, count(DISTINCT agent_version) AS n_versions
                FROM sessions
                GROUP BY user_id, experiment_id
                HAVING count(DISTINCT agent_version) > 1
                """
            )
        ).fetchall()
    assert rows == [], f"{len(rows)} users have inconsistent agent_version across sessions in the same experiment"


def test_assignment_matches_deterministic_hash_function(db_engine):
    """Re-derive the assignment independently from user_id+experiment_id and
    confirm it matches what's stored — catches any accidental session-level
    (rather than user-level) randomization creeping into the generator."""
    from datagen.assignment import assign_agent_version

    with db_engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT user_id, experiment_id, agent_version FROM sessions")).fetchall()
    assert len(rows) > 0
    for user_id, experiment_id, agent_version in rows:
        assert assign_agent_version(user_id, experiment_id) == agent_version


def test_treatment_balance_is_reasonable(db_engine):
    """Hash-based assignment should be close to 50/50 at the user level; a
    small deviation is expected sampling noise at dev scale (see the
    Stage 1 deliverable report), but a large skew would indicate a biased
    hash or a broken assignment path."""
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT user_id, agent_version FROM sessions")
        ).fetchall()
    versions = [r[1] for r in rows]
    n = len(versions)
    n_v2 = sum(1 for v in versions if v == "v2")
    share_v2 = n_v2 / n
    assert 0.35 < share_v2 < 0.65, f"user-level v2 share {share_v2:.3f} is implausibly far from 50/50"
