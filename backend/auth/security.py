"""Password hashing (bcrypt) and JWT issuing/verification (Stage 7 task 1).

Production-plausible but deliberately minimal: HS256 JWTs signed with a
secret from AIPI_JWT_SECRET (a fixed local-dev default is used if unset —
fine for this portfolio deployment, called out explicitly in the Stage 7
report as a blocker before a real deployment). No SSO, no refresh-token
rotation, no session store — a bearer access token only, as scoped.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

JWT_SECRET = os.environ.get("AIPI_JWT_SECRET", "dev-only-insecure-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=24)


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
