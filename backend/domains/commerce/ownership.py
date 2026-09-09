"""Stage 8 task 3/4: the commerce demo dataset is a single, fixed,
never-duplicated set of rows (loaded once by datagen) — it does not get a
separate copy per project the way the generic ingestion layer's data
does. Instead, exactly one project "owns" it at a time, recorded on
experiments.project_id (backend/app/models/core.py).

Claiming is a deliberate, explicit administrative action (a script, not a
regular API endpoint one calls as part of normal product use) — never
triggered automatically by creating a project, so that creating a SECOND
commerce-domain project to prove isolation never silently steals
ownership away from whichever project already holds it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def claim_commerce_dataset(engine: Engine, project_id: str) -> int:
    """Unconditionally (re)assigns every commerce experiment (and,
    transitively, every session under it) to `project_id`. Idempotent —
    claiming the dataset you already own is a no-op in effect — and safe
    to call whether the dataset is currently unclaimed (project_id IS
    NULL, e.g. right after this migration or on a fresh demo load) or
    already claimed by a different project (explicit reassignment).
    Returns the number of experiment rows updated.
    """
    with engine.begin() as conn:
        result = conn.execute(text("UPDATE experiments SET project_id = :pid"), {"pid": project_id})
        return result.rowcount


def get_commerce_dataset_owner(engine: Engine) -> str | None:
    """The project_id currently claiming the dataset, or None if
    unclaimed (or if there are no experiments at all). Only meaningful
    while every experiment row shares one project_id, which
    claim_commerce_dataset guarantees by always setting all of them
    together."""
    with engine.connect() as conn:
        return conn.execute(text("SELECT DISTINCT project_id FROM experiments LIMIT 1")).scalar()
