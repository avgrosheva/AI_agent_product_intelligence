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
