"""Deterministic UUID generation.

DATA_MODEL.md SS7 warns explicitly about UUID generation being a common
source of accidental nondeterminism (uuid.uuid4() draws from os.urandom,
which is not seeded and not reproducible). Every id in this generator is
instead derived from uuid.uuid5 (name-based, SHA-1 hash of a namespace +
name string) seeded by (profile, seed, entity, index) — fully
deterministic and independent of the numpy RNG stream, so id generation
never perturbs how many "real" random draws downstream code consumes.
"""

import uuid

_ROOT_NAMESPACE = uuid.UUID("7f3b6d2a-1c4e-4a8b-9f2d-6e1a9c3b5d7f")


def entity_id(profile: str, seed: int, entity: str, index: int) -> uuid.UUID:
    """Deterministic id for the `index`-th row of `entity` in this run."""
    name = f"{profile}:{seed}:{entity}:{index}"
    return uuid.uuid5(_ROOT_NAMESPACE, name)


def child_id(profile: str, seed: int, entity: str, parent_index: int, child_index: int) -> uuid.UUID:
    """Deterministic id for a child row (e.g. the 3rd message of session 42)."""
    name = f"{profile}:{seed}:{entity}:{parent_index}:{child_index}"
    return uuid.uuid5(_ROOT_NAMESPACE, name)
