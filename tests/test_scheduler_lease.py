"""Stage 18 task 5/11: the database-backed scheduler lease
(backend.monitoring.lease) that lets several backend instances run
MonitoringScheduler identically without every one of them redundantly
scanning for due jobs each poll interval — only the current lease holder
does. Uses a fresh lease_key per test (uuid-suffixed) so tests never
collide with each other or with a real scheduler thread that might be
running against the same test database."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.monitoring.lease import get_lease_state, release_lease, try_acquire_or_renew_lease


def _key() -> str:
    return f"test-lease-{uuid.uuid4().hex[:8]}"


def test_first_acquire_succeeds(db_engine):
    key = _key()
    assert try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=30) is True
    state = get_lease_state(db_engine, key)
    assert state is not None
    assert state.holder_id == "instance-a"
    assert state.is_active


def test_a_different_instance_cannot_steal_a_still_live_lease(db_engine):
    key = _key()
    assert try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=30) is True
    assert try_acquire_or_renew_lease(db_engine, key, "instance-b", ttl_seconds=30) is False
    # The lease still belongs to instance-a -- instance-b's failed attempt
    # must not have clobbered it.
    assert get_lease_state(db_engine, key).holder_id == "instance-a"


def test_the_current_holder_can_renew_its_own_lease(db_engine):
    key = _key()
    assert try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=30) is True
    first_expiry = get_lease_state(db_engine, key).expires_at
    assert try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=60) is True
    second_expiry = get_lease_state(db_engine, key).expires_at
    assert second_expiry > first_expiry


def test_another_instance_can_claim_an_expired_lease(db_engine):
    key = _key()
    assert try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=30) is True
    # Force expiry directly rather than sleeping -- deterministic, no
    # test-timing flakiness.
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE scheduler_leases SET expires_at = :past WHERE lease_key = :key"),
            {"past": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1), "key": key},
        )
    assert try_acquire_or_renew_lease(db_engine, key, "instance-b", ttl_seconds=30) is True
    assert get_lease_state(db_engine, key).holder_id == "instance-b"


def test_release_only_removes_a_lease_this_holder_still_owns(db_engine):
    key = _key()
    try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=30)

    # A non-owner's release call is a no-op -- it must never delete
    # someone else's still-live lease.
    release_lease(db_engine, key, "instance-b")
    assert get_lease_state(db_engine, key) is not None

    release_lease(db_engine, key, "instance-a")
    assert get_lease_state(db_engine, key) is None


def test_only_one_of_two_concurrently_polling_instances_wins_a_given_cycle(db_engine):
    """The core multi-instance-safety property Stage 18 task 5 asks for:
    simulates two backend instances polling in the same instant (the
    realistic race) by calling try_acquire_or_renew_lease with two
    different holder_ids back-to-back for the SAME key with no lease yet
    held — exactly one of them may proceed to treat itself as "the
    scheduler" for that cycle."""
    key = _key()
    results = [
        try_acquire_or_renew_lease(db_engine, key, "instance-a", ttl_seconds=90),
        try_acquire_or_renew_lease(db_engine, key, "instance-b", ttl_seconds=90),
    ]
    assert results == [True, False]
