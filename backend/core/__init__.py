"""Domain-agnostic core: types and generic mechanisms that any agent
product (not just this project's shopping demo) could reuse.

Hard rule, enforced by tests/test_core_domain_isolation.py: nothing under
backend/core/ may import backend.app.models (the commerce ORM models —
Product, Recommendation, etc.), backend.domains.*, or any commerce-flavored
enum/string vocabulary. Domain-specific data and detectors live in
backend/domains/<domain_name>/ instead — backend/domains/commerce/ is the
one that backs the current shopping demo.

This package intentionally does not replace or move existing domain code
(SessionContext, MechanismResult, evaluate_guardrails, the metric registry)
— those keep working exactly as before. It adds the generic layer those
concrete, commerce-specific implementations now sit on top of: a
mechanism/guardrail can be REGISTERED generically here, and the commerce
domain module supplies the actual shopping-agent mechanisms/guardrails as
data, not by hand-coding a second, parallel abstraction.
"""
