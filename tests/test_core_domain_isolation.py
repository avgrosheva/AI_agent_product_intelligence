"""Stage 2 (domain-agnostic core) structural guarantees:

- backend/core/ never imports the commerce ORM models, backend/domains/*,
  or references shopping-specific vocabulary in its own source.
- The commerce domain's mechanism/guardrail registries produce exactly
  the same values as the hardcoded constants they replaced (no behavior
  drift from the Stage 2 refactor).
- backend/investigation/ (the generic Investigation engine) does not
  import the commerce ORM models directly — it only ever receives
  session-level dataframes and domain-registered mechanism/guardrail data.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil

import backend.core

FORBIDDEN_IMPORT_PREFIXES = ("backend.app.models", "backend.domains")
FORBIDDEN_SUBSTRINGS = (
    "product", "recommendation", "constraint", "requested_category",
    "satisfies_constraints", "cart", "purchase",
)


def _iter_core_modules():
    for _, name, _ in pkgutil.walk_packages(backend.core.__path__, prefix="backend.core."):
        yield importlib.import_module(name)


def test_core_package_never_imports_commerce_orm_models_or_domains():
    for module in _iter_core_modules():
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                    assert not node.module.startswith(forbidden), (
                        f"{module.__name__} imports from {node.module}, which starts with forbidden prefix {forbidden!r}"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                        assert not alias.name.startswith(forbidden), (
                            f"{module.__name__} imports {alias.name}, which starts with forbidden prefix {forbidden!r}"
                        )


def _source_without_docstrings(module) -> str:
    """Module source with every docstring (module, class, function) removed,
    so a docstring that legitimately NAMES a forbidden concept to explain
    why the code never touches it doesn't trip a search for actual code
    references to that concept — same approach as
    tests/test_api_no_ground_truth_leakage.py."""
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


def test_core_package_source_has_no_commerce_vocabulary():
    """Docstrings are allowed to explain what core is NOT coupled to (they
    necessarily name the concepts being disclaimed) — only executable code
    is checked."""
    for module in _iter_core_modules():
        code_only = _source_without_docstrings(module).lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in code_only, f"{module.__name__}'s executable code references {forbidden!r}"


def test_investigation_package_never_imports_commerce_orm_models():
    import backend.investigation

    for _, name, _ in pkgutil.walk_packages(backend.investigation.__path__, prefix="backend.investigation."):
        module = importlib.import_module(name)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend.app.models"):
                raise AssertionError(f"{module.__name__} imports commerce ORM models from {node.module}")


def test_commerce_mechanism_registry_matches_the_values_it_replaced():
    from backend.llm.client import DETERMINISTIC_MECHANISMS, FAILURE_MECHANISMS, SEMANTIC_MECHANISMS

    assert DETERMINISTIC_MECHANISMS == ("retrieval_failure", "poor_ranking", "wrong_tool_selection")
    assert SEMANTIC_MECHANISMS == ("unnecessary_clarification", "wrong_constraint_interpretation", "unsupported_product_claim")
    assert FAILURE_MECHANISMS == DETERMINISTIC_MECHANISMS + SEMANTIC_MECHANISMS


def test_mechanism_registry_is_generic_and_rejects_duplicate_names():
    from backend.core.attribution import Mechanism, MechanismRegistry

    registry = MechanismRegistry([Mechanism("a", "deterministic"), Mechanism("b", "semantic")])
    assert registry.deterministic == ("a",)
    assert registry.semantic == ("b",)
    assert registry.all_names == ("a", "b")
    assert "a" in registry and "z" not in registry

    import pytest

    with pytest.raises(ValueError):
        MechanismRegistry([Mechanism("a", "deterministic"), Mechanism("a", "semantic")])


def test_evaluate_guardrails_is_generic_and_domain_data_free():
    """The generic evaluator works given ANY GuardrailDefinition list, not
    just the commerce one — proven with synthetic column names."""
    import pandas as pd

    from backend.core.guardrails import GuardrailDefinition, evaluate_guardrails

    df = pd.DataFrame(
        {
            "agent_version": ["v1"] * 10 + ["v2"] * 10,
            "resolution_time_seconds": [100.0] * 10 + [130.0] * 10,
        }
    )
    definitions = [
        GuardrailDefinition(
            name="p95_resolution_time",
            column="resolution_time_seconds",
            aggregation="p95_raw",
            comparison="ratio",
            threshold=1.1,
        )
    ]
    report = evaluate_guardrails(df, definitions)
    assert len(report.checks) == 1
    assert report.checks[0].breached is True
    assert report.any_breach is True


def _assert_package_never_imports_commerce_orm_models(package):
    # backend.app.models.base (the shared SQLAlchemy declarative Base) is
    # deliberately allowed: it's generic infrastructure (one metadata/
    # migration history for the whole app), not a commerce ORM model —
    # the forbidden thing is depending on Product/Recommendation/Session/
    # etc. (backend.app.models.core/.sessions/.outcomes).
    allowed = {"backend.app.models.base"}
    for _, name, _ in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        module = importlib.import_module(name)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend.app.models") and node.module not in allowed:
                raise AssertionError(f"{module.__name__} imports commerce ORM models from {node.module}")


def test_ingestion_package_never_imports_commerce_orm_models():
    """Stage 3: the generic ingestion layer (schemas/models/service) must
    never depend on the commerce ORM models — it has its own, separate
    storage tables."""
    import backend.ingestion

    _assert_package_never_imports_commerce_orm_models(backend.ingestion)


def test_support_domain_never_imports_commerce_orm_models_or_commerce_domain():
    """Stage 3 proof: a second, non-commerce domain adapter is buildable
    without any dependency on backend.app.models OR backend.domains.commerce."""
    import backend.domains.support

    _assert_package_never_imports_commerce_orm_models(backend.domains.support)

    for _, name, _ in pkgutil.walk_packages(backend.domains.support.__path__, prefix="backend.domains.support."):
        module = importlib.import_module(name)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend.domains.commerce"):
                raise AssertionError(f"{module.__name__} imports the commerce domain from {node.module}")


def test_domain_adapter_protocol_is_satisfied_structurally_by_both_domains():
    """Both CommerceAdapter and SupportAdapter expose the same
    DomainAdapter-shaped surface (duck-typed, no inheritance required)."""
    from backend.core.adapter import DomainAdapter
    from backend.domains.commerce.adapter import CommerceAdapter
    from backend.domains.support.adapter import SupportAdapter

    required_methods = [name for name in dir(DomainAdapter) if not name.startswith("_")]
    for adapter_cls in (CommerceAdapter, SupportAdapter):
        for method in required_methods:
            assert hasattr(adapter_cls, method), f"{adapter_cls.__name__} is missing DomainAdapter method {method!r}"
