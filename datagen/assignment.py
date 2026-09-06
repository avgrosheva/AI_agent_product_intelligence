"""User-level experiment assignment (DATA_MODEL.md SS3.4, SS1).

The user, not the session, is the randomization unit: every session a
given user has inside a given experiment gets the same agent_version.
Uses hashlib (not Python's built-in hash()) because hash() is salted per
process via PYTHONHASHSEED and is NOT reproducible across runs/machines —
using it here would silently break the reproducibility guarantee.
"""

import hashlib
import uuid


def assign_agent_version(user_id: uuid.UUID, experiment_id: uuid.UUID) -> str:
    digest = hashlib.sha256(f"{user_id}|{experiment_id}".encode("utf-8")).digest()
    return "v2" if digest[0] % 2 == 0 else "v1"
