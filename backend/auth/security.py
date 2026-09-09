"""Password hashing (bcrypt) and JWT issuing/verification (Stage 7 task 1).

Production-plausible but deliberately minimal: HS256 JWTs signed with a
secret from AIPI_JWT_SECRET. No SSO, no refresh-token rotation, no
session store — a bearer access token only, as scoped.

Stage 8 task 5: AIPI_ENV distinguishes "development"/"test" (the fixed
dev secret below is accepted — nothing about local dev or the test suite
sets AIPI_JWT_SECRET) from anything else (read: "production" or any
environment name an operator chooses for a real deployment), where
running with the fixed dev secret is refused at import time — a
misconfigured deployment fails loudly on startup instead of silently
issuing tokens anyone who has read this file's source could forge.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

DEV_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-in-production"
_DEV_ENVIRONMENTS = {"development", "test"}

ENV = os.environ.get("AIPI_ENV", "development")
JWT_SECRET = os.environ.get("AIPI_JWT_SECRET", DEV_DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=24)

if ENV not in _DEV_ENVIRONMENTS and JWT_SECRET == DEV_DEFAULT_JWT_SECRET:
    raise RuntimeError(
        f"AIPI_ENV={ENV!r} (outside {_DEV_ENVIRONMENTS}) requires AIPI_JWT_SECRET to be set to a "
        "real secret — refusing to start with the fixed development JWT secret, which is "
        "readable in this project's own source and would let anyone forge a valid token."
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user_id (the "sub" claim). Raises jwt.PyJWTError
    (InvalidTokenError, ExpiredSignatureError, ...) on any problem — the
    caller (backend.app.auth_deps.get_current_user) turns that into 401."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return payload["sub"]
