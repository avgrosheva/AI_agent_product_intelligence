"""Auth/tenancy storage (Stage 7 tasks 1-2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base

ROLES = ("admin", "analyst", "viewer")
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}


class PlatformUser(Base):
    # Not "User": that class name is already taken by the commerce domain's
    # own ORM model (shopping personas, backend/app/models/core.py), and
    # SQLAlchemy's declarative registry indexes mapped classes by class
    # name for string-based relationship resolution — two classes named
    # "User" anywhere in the same registry collide
    # (InvalidRequestError: "Multiple classes found for path 'User'"), even
    # when they map to different tables. Table name is unrelated to any
    # domain's data either way.
    __tablename__ = "platform_users"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class Organization(Base):
    __tablename__ = "organizations"

    org_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    membership_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)  # "admin" | "analyst" | "viewer"
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_memberships_org_user"),)


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False, index=True)  # "commerce" | "support" | ...
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class RefreshToken(Base):
    # Stage 18 task 4: a short-lived JWT access token
    # (backend.auth.security.ACCESS_TOKEN_TTL) plus a long-lived, revocable
    # refresh token -- the access token stays a stateless,
    # unrevokable-until-expiry JWT (fine at a short TTL now), while the
    # refresh token is real server state so it can actually be revoked (a
    # single logout, or "log out everywhere"). Only the SHA-256 hash of
    # the token is stored, matching a password-reset-token/API-key
    # convention -- the plaintext token is bearer-equivalent to a login,
    # so a stolen database dump must not itself be enough to authenticate
    # as anyone (the same reason passwords are hashed, not
    # encrypted-and-decryptable).
    __tablename__ = "refresh_tokens"

    token_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Rotation chain: set on the OLD token the moment it's exchanged for a
    # new one, so a token that's already been rotated can be told apart
    # from one that's merely expired or was explicitly logged out --
    # useful signal if a reused (already-rotated) refresh token ever shows
    # up, the classic sign of a stolen token being replayed.
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
