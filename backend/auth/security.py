"""Password hashing (bcrypt), JWT issuing/verification, and refresh-token
primitives (Stage 7 task 1; hardened Stage 18 task 4).

Production-plausible but deliberately minimal: HS256 JWTs signed with a
secret from AIPI_JWT_SECRET. No SSO, no password reset, no email
verification — those stay explicitly out of scope per the Stage 18 brief.

Stage 18 task 4: the access token is now SHORT-lived
(ACCESS_TOKEN_TTL, 15 minutes) rather than the original 24 hours, paired
with a separate, long-lived, REVOCABLE refresh token
(backend.auth.models.RefreshToken) that a caller exchanges for a fresh
access token via POST /api/v1/auth/refresh. The access token itself
stays a stateless JWT with no server-side revocation list — at a 15
-minute TTL, the blast radius of "issued but not yet expired" is small
enough that this project's actual attack surface (rotation the moment a
refresh token is reused after being replaced, logout, and "log out
everywhere") lives entirely in the refresh-token table instead, where
revocation is real. A refresh token is a high-entropy random string
(generate_refresh_token), never a JWT itself — nothing about it needs to
be self-describing, and storing only its hash (hash_refresh_token) means
a stolen database dump can't be replayed as a valid session, the same
property password hashing gives login credentials.

Stage 8 task 5: AIPI_ENV distinguishes "development"/"test" (the fixed
dev secret below is accepted — nothing about local dev or the test suite
sets AIPI_JWT_SECRET) from anything else (read: "production" or any
environment name an operator chooses for a real deployment), where
running with the fixed dev secret is refused at import time — a
misconfigured deployment fails loudly on startup instead of silently
issuing tokens anyone who has read this file's source could forge.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

DEV_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-in-production"
_DEV_ENVIRONMENTS = {"development", "test"}

ENV = os.environ.get("AIPI_ENV", "development")
JWT_SECRET = os.environ.get("AIPI_JWT_SECRET", DEV_DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)

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


def generate_refresh_token() -> str:
    # 48 bytes of urlsafe-base64 entropy -- far beyond brute-force range,
    # and opaque (unlike the access token, nothing ever needs to decode a
    # claim out of this one; its only job is to be looked up by hash).
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # SHA-256, not bcrypt: this token is already 48 bytes of high-entropy
    # random data (unlike a human-chosen password), so it needs no
    # deliberately-slow, salted hash to resist brute force — a fast,
    # deterministic hash is exactly what a lookup-by-hash needs.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
