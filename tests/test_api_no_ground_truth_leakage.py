"""Cross-cutting checks that no endpoint response, and the OpenAPI schema
itself, exposes validation_ground_truth.parquet, planted-effect
identifiers, generator ground truth, or validation-only labels
(Stage 4 constraint)."""

from __future__ import annotations

import ast
import inspect
import json

FORBIDDEN_SUBSTRINGS = [
    "ground_truth", "validation_ground_truth", "planted_scenario", "generator_effect",
    "overclarify_v2", "android_latency", "monitor_constraint_regression_v2",
    "exploratory_uplift", "tool_selection_v2_improved",
]


def _assert_response_is_clean(body: dict) -> None:
    text = json.dumps(body)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in text, f"response leaked forbidden term: {forbidden}"


def _source_without_docstrings(module) -> str:
    """Module source with every docstring (module, class, and function)
    removed, so a docstring that legitimately NAMES a forbidden concept to
    explain why the code never touches it doesn't trip a search for actual
    code references to that concept."""
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body[0] = ast.Pass()
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def test_experiments_list_is_clean(api_client):
    resp = api_client.get("/experiments")
    _assert_response_is_clean(resp.json())


def test_experiment_metrics_is_clean(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/metrics")
    _assert_response_is_clean(resp.json())


def test_investigation_response_is_clean_for_every_lens(api_client, experiment_id):
    for lens in ("abandonment", "conversion", "constraint_satisfaction"):
        resp = api_client.get(f"/experiments/{experiment_id}/investigation", params={"lens": lens})
        _assert_response_is_clean(resp.json())


def test_session_list_is_clean(api_client):
    resp = api_client.get("/sessions", params={"limit": 100})
    _assert_response_is_clean(resp.json())


def test_session_detail_is_clean(api_client):
    session_id = api_client.get("/sessions", params={"limit": 1}).json()["items"][0]["session_id"]
    resp = api_client.get(f"/sessions/{session_id}")
    _assert_response_is_clean(resp.json())


def test_ai_quality_is_clean(api_client, experiment_id):
    resp = api_client.get(f"/experiments/{experiment_id}/ai-quality")
    _assert_response_is_clean(resp.json())
    resp2 = api_client.get("/ai-quality/classifier-evaluation")
    _assert_response_is_clean(resp2.json())


def test_openapi_schema_has_no_ground_truth_fields(api_client):
    """Checks schema FIELD NAMES only, not free-text descriptions — a
    description legitimately explaining "this endpoint never exposes
    ground truth" necessarily contains the word, which is not a leak."""
    resp = api_client.get("/openapi.json")
    assert resp.status_code == 200
    schemas = resp.json().get("components", {}).get("schemas", {})
    for schema_name, schema in schemas.items():
        for prop_name in schema.get("properties", {}):
            for forbidden in FORBIDDEN_SUBSTRINGS:
                assert forbidden not in prop_name, f"{schema_name}.{prop_name} is a forbidden field name"


def test_no_router_source_references_validation_artifact():
    """Structural guard, same discipline as backend.investigation/backend.llm:
    router CODE (docstrings excluded, since one legitimately names the
    artifact to disclaim reading it) must never reference it."""
    from backend.app.routers import ai_quality, experiments, investigation, sessions

    for module in (ai_quality, experiments, investigation, sessions):
        source = _source_without_docstrings(module)
        assert "validation_ground_truth" not in source, f"{module.__name__} code references validation_ground_truth"
        assert "generation_manifest" not in source, f"{module.__name__} code references generation_manifest"
