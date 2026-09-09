"""Stage 5 composition root for the generic, domain-parametrized API
(backend.app.routers.domains): the one place in `backend.app` allowed to
know about concrete domain packages (backend.domains.commerce,
backend.domains.support). Every generic router/service module downstream
of this (backend.app.routers.domains, backend.release.*,
backend.investigation.*, backend.core.*) receives only a DomainAdapter
instance or its derived InvestigationConfig — never imports a domain
package directly.

Adding a third domain means adding one entry here; nothing else in the
generic API surface changes.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.app.db import get_database_url
from backend.core.adapter import DomainAdapter
from backend.domains.commerce.adapter import CommerceAdapter
from backend.domains.support.adapter import SupportAdapter

_ADAPTER_CLASSES: dict[str, type] = {
    "commerce": CommerceAdapter,
    "support": SupportAdapter,
}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """A separate cached engine from backend.app.dependencies.get_engine()
    (same underlying database, same lru_cache pattern) so this module — the
    one place the generic API is allowed to know about concrete domains —
    never has to import backend.app.dependencies, which itself imports
    backend.llm.client (a commerce-coupled module) at module scope."""
    return create_engine(get_database_url())


def available_domains() -> list[str]:
    return sorted(_ADAPTER_CLASSES)


def get_adapter(domain: str) -> DomainAdapter:
    adapter_cls = _ADAPTER_CLASSES.get(domain)
    if adapter_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown domain '{domain}'. Available: {available_domains()}")
    return adapter_cls(get_engine())
