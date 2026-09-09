"""Stage 7 tasks 1-3: user registration/login, organizations, memberships
(with role), and projects. Pure data-layer service — no FastAPI imports
here (those live in backend.app.auth_deps), no domain package imports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from backend.auth.models import ROLE_RANK, ROLES, Organization, OrganizationMembership, Project, PlatformUser
from backend.auth.security import create_access_token, hash_password, verify_password


class AuthError(Exception):
    """Raised for invalid credentials / duplicate email — the router maps
    this to a 401/409, never leaking which one it was for login (to avoid
    user enumeration) but distinguishing them for registration."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


@dataclass(frozen=True)
class UserResult:
    user_id: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class OrganizationResult:
    org_id: str
    name: str
    created_at: datetime


@dataclass(frozen=True)
class MembershipResult:
    membership_id: str
    org_id: str
    user_id: str
    email: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectResult:
    project_id: str
    org_id: str
    name: str
    domain: str
    created_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def register_user(engine: Engine, email: str, password: str) -> UserResult:
    now = _now()
    user_id = uuid.uuid4()
    with OrmSession(engine) as session:
        row = PlatformUser(user_id=user_id, email=email.lower().strip(), password_hash=hash_password(password), created_at=now)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise EmailAlreadyRegistered(f"'{email}' is already registered")
        return UserResult(user_id=str(row.user_id), email=row.email, created_at=row.created_at)


def authenticate_user(engine: Engine, email: str, password: str) -> str:
    """Returns a signed access token, or raises InvalidCredentials."""
    with OrmSession(engine) as session:
        row = session.execute(select(PlatformUser).where(PlatformUser.email == email.lower().strip())).scalar_one_or_none()
    if row is None or not verify_password(password, row.password_hash):
        raise InvalidCredentials("invalid email or password")
    return create_access_token(str(row.user_id))


def get_user(engine: Engine, user_id: str) -> UserResult | None:
    with OrmSession(engine) as session:
        row = session.get(PlatformUser, uuid.UUID(user_id))
    return UserResult(user_id=str(row.user_id), email=row.email, created_at=row.created_at) if row else None


def create_organization(engine: Engine, name: str, owner_user_id: str) -> OrganizationResult:
    """The creator becomes the org's first admin — same "create your own
    workspace" pattern as most B2B SaaS onboarding."""
    now = _now()
    org_id = uuid.uuid4()
    with OrmSession(engine) as session:
        org = Organization(org_id=org_id, name=name, created_at=now)
        session.add(org)
        session.flush()
        session.add(OrganizationMembership(membership_id=uuid.uuid4(), org_id=org_id, user_id=uuid.UUID(owner_user_id), role="admin", created_at=now))
        session.commit()
        return OrganizationResult(org_id=str(org.org_id), name=org.name, created_at=org.created_at)


def get_membership(engine: Engine, org_id: str, user_id: str) -> MembershipResult | None:
    with OrmSession(engine) as session:
        row = session.execute(
            select(OrganizationMembership, PlatformUser)
            .join(PlatformUser, PlatformUser.user_id == OrganizationMembership.user_id)
            .where(OrganizationMembership.org_id == uuid.UUID(org_id), OrganizationMembership.user_id == uuid.UUID(user_id))
        ).first()
    if row is None:
        return None
    m, u = row
    return MembershipResult(membership_id=str(m.membership_id), org_id=str(m.org_id), user_id=str(m.user_id), email=u.email, role=m.role, created_at=m.created_at)


def add_member(engine: Engine, org_id: str, email: str, role: str) -> MembershipResult:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    now = _now()
    with OrmSession(engine) as session:
        user = session.execute(select(PlatformUser).where(PlatformUser.email == email.lower().strip())).scalar_one_or_none()
        if user is None:
            raise ValueError(f"no registered user with email '{email}'")
        existing = session.execute(
            select(OrganizationMembership).where(OrganizationMembership.org_id == uuid.UUID(org_id), OrganizationMembership.user_id == user.user_id)
        ).scalar_one_or_none()
        if existing is not None:
            existing.role = role
            session.commit()
            membership_id = existing.membership_id
        else:
            membership_id = uuid.uuid4()
            session.add(OrganizationMembership(membership_id=membership_id, org_id=uuid.UUID(org_id), user_id=user.user_id, role=role, created_at=now))
            session.commit()
        return MembershipResult(membership_id=str(membership_id), org_id=org_id, user_id=str(user.user_id), email=user.email, role=role, created_at=now)


def list_members(engine: Engine, org_id: str) -> list[MembershipResult]:
    with OrmSession(engine) as session:
        rows = session.execute(
            select(OrganizationMembership, PlatformUser)
            .join(PlatformUser, PlatformUser.user_id == OrganizationMembership.user_id)
            .where(OrganizationMembership.org_id == uuid.UUID(org_id))
        ).all()
    return [
        MembershipResult(membership_id=str(m.membership_id), org_id=str(m.org_id), user_id=str(m.user_id), email=u.email, role=m.role, created_at=m.created_at)
        for m, u in rows
    ]


def list_user_memberships(engine: Engine, user_id: str) -> list[MembershipResult]:
    with OrmSession(engine) as session:
        rows = session.execute(
            select(OrganizationMembership, PlatformUser)
            .join(PlatformUser, PlatformUser.user_id == OrganizationMembership.user_id)
            .where(OrganizationMembership.user_id == uuid.UUID(user_id))
        ).all()
    return [
        MembershipResult(membership_id=str(m.membership_id), org_id=str(m.org_id), user_id=str(m.user_id), email=u.email, role=m.role, created_at=m.created_at)
        for m, u in rows
    ]


def create_project(engine: Engine, org_id: str, name: str, domain: str) -> ProjectResult:
    now = _now()
    project_id = uuid.uuid4()
    with OrmSession(engine) as session:
        row = Project(project_id=project_id, org_id=uuid.UUID(org_id), name=name, domain=domain, created_at=now)
        session.add(row)
        session.commit()
        return ProjectResult(project_id=str(row.project_id), org_id=str(row.org_id), name=row.name, domain=row.domain, created_at=row.created_at)


def get_project(engine: Engine, project_id: str) -> ProjectResult | None:
    with OrmSession(engine) as session:
        row = session.get(Project, uuid.UUID(project_id))
    return ProjectResult(project_id=str(row.project_id), org_id=str(row.org_id), name=row.name, domain=row.domain, created_at=row.created_at) if row else None


def list_org_projects(engine: Engine, org_id: str) -> list[ProjectResult]:
    with OrmSession(engine) as session:
        rows = session.execute(select(Project).where(Project.org_id == uuid.UUID(org_id))).scalars().all()
    return [ProjectResult(project_id=str(r.project_id), org_id=str(r.org_id), name=r.name, domain=r.domain, created_at=r.created_at) for r in rows]


def list_user_projects_for_domain(engine: Engine, user_id: str, domain: str) -> list[ProjectResult]:
    """Every project, across every org the user belongs to, whose domain
    matches — used to resolve an implicit project when the caller doesn't
    pass project_id explicitly (backend.app.auth_deps.get_project_context)."""
    org_ids = [m.org_id for m in list_user_memberships(engine, user_id)]
    if not org_ids:
        return []
    with OrmSession(engine) as session:
        rows = session.execute(
            select(Project).where(Project.org_id.in_([uuid.UUID(o) for o in org_ids]), Project.domain == domain)
        ).scalars().all()
    return [ProjectResult(project_id=str(r.project_id), org_id=str(r.org_id), name=r.name, domain=r.domain, created_at=r.created_at) for r in rows]


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK[role] >= ROLE_RANK[minimum]
