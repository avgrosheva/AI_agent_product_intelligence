"""Security fix regression coverage: the pre-Stage-7 legacy routers
(experiments, investigation, sessions, and the one unscoped route that
used to live in ai_quality) took only get_current_user -- any
authenticated user of ANY org -- and looked records up by bare UUID with
no project/org ownership check at all. Any signed-in user who obtained
another org's experiment or session id (leaked link, shared screenshot)
could read that org's full metrics, investigation findings, AI-quality
data, and raw session transcripts.

Fix: backend.app.main no longer mounts experiments.router,
investigation.router, or sessions.router at all, and
backend.app.routers.ai_quality no longer defines the one route that read
experiment-scoped data (GET /experiments/{id}/ai-quality). These tests
prove every one of those paths is genuinely gone -- not just gated -- for
EVERY authenticated caller, including the legitimate owner of the very
data being requested (the strongest possible proof: if even the rightful
owner can't reach it through the old path, no cross-tenant reader can
either). The equivalent, project-scoped data remains reachable, unchanged,
through GET /api/v1/domains/{domain}/... (see test_generic_domain_api.py
and test_rbac.py for that API's own ownership-check coverage), and the
one legitimately non-tenant route in ai_quality.router
(/ai-quality/classifier-evaluation) is confirmed still live and unaffected.
"""

from __future__ import annotations

import pytest


LEGACY_ROUTES_REQUIRING_A_REAL_EXPERIMENT_ID = [
    "/experiments/{experiment_id}",
    "/experiments/{experiment_id}/metrics",
    "/experiments/{experiment_id}/funnel",
    "/experiments/{experiment_id}/guardrails",
    "/experiments/{experiment_id}/investigation",
    "/experiments/{experiment_id}/ai-quality",
]


@pytest.mark.parametrize("path_template", LEGACY_ROUTES_REQUIRING_A_REAL_EXPERIMENT_ID)
def test_legacy_experiment_scoped_routes_are_gone_even_for_the_datas_own_owner(api_client, experiment_id, path_template):
    """`experiment_id` is a REAL experiment the authenticated caller's own
    org legitimately owns -- proving even its rightful owner can no longer
    reach it through the old bare path is a stronger guarantee than
    checking a stranger's id would be (a 404 for a nonexistent id proves
    nothing about whether the route itself still exists)."""
    resp = api_client.get(path_template.format(experiment_id=experiment_id))
    assert resp.status_code == 404


def test_legacy_experiments_list_route_is_gone(api_client):
    resp = api_client.get("/experiments")
    assert resp.status_code == 404


def test_legacy_sessions_list_route_is_gone(api_client):
    resp = api_client.get("/sessions")
    assert resp.status_code == 404


def test_legacy_session_detail_route_is_gone_even_for_a_real_session(api_client, experiment_id):
    """Same "even the owner can't" proof as above, for a session id drawn
    from the caller's own real, owned data via the surviving generic API."""
    sessions = api_client.get(
        "/api/v1/domains/commerce/sessions", params={"experiment_id": experiment_id, "limit": 1}
    ).json()["items"]
    assert sessions, "expected the dev fixture to have at least one commerce session"
    real_session_id = sessions[0]["session_id"]

    resp = api_client.get(f"/sessions/{real_session_id}")
    assert resp.status_code == 404


def test_legacy_routes_gone_regardless_of_id_validity(api_client):
    """A malformed or nonexistent id must 404 the same way a real one
    does -- proving the route itself is unmounted, not merely raising its
    own 404 for a bad lookup."""
    for path in (
        "/experiments/not-a-uuid",
        "/experiments/00000000-0000-0000-0000-000000000000",
        "/experiments/00000000-0000-0000-0000-000000000000/investigation",
        "/experiments/00000000-0000-0000-0000-000000000000/ai-quality",
        "/sessions/not-a-uuid",
        "/sessions/00000000-0000-0000-0000-000000000000",
    ):
        resp = api_client.get(path)
        assert resp.status_code == 404, f"{path} should be unreachable (got {resp.status_code})"


def test_legacy_routes_unreachable_without_auth_too(api_client):
    """Belt-and-suspenders: not mounted beats not authenticated -- an
    anonymous caller gets the same 404 (route not found), never a 401
    that would confirm the path still exists behind auth."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as anon_client:
        resp = anon_client.get("/experiments")
        assert resp.status_code == 404


def test_classifier_evaluation_route_is_unaffected(api_client):
    """The one ai_quality.router route that was never part of this bug
    (reads only a global, non-tenant classifier benchmark artifact) stays
    mounted and working exactly as before -- this fix has zero
    compatibility impact on it."""
    resp = api_client.get("/ai-quality/classifier-evaluation")
    assert resp.status_code == 200
    assert "provenance" in resp.json()


def test_generic_domain_scoped_equivalents_still_serve_the_same_kind_of_data(api_client, experiment_id):
    """The fix must not have collaterally broken the real, project-scoped
    replacement API -- same experiment, reached the correct (secured) way."""
    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/metrics")
    assert resp.status_code == 200
    assert len(resp.json()["metrics"]) > 0

    resp = api_client.get(f"/api/v1/domains/commerce/experiments/{experiment_id}/ai-quality")
    assert resp.status_code == 200
