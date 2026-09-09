"""Stage 7: FastAPI auth/tenancy dependencies shared by every router.

get_current_user requires a valid `Authorization: Bearer <token>` header.
get_project_context additionally resolves WHICH project a request acts on
(explicit `project_id` query param, or — the common single-project case —
inferred from the caller's own memberships when it's unambiguous) and
checks the caller is actually a member of that project's organization.
require_role(...) then gates write actions by the caller's role in that
project's organization (Stage 7 task 3).
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Query

from backend.app.domain_registry import available_domains, get_engine
from backend.auth.models import ROLE_RANK
from backend.auth.security import decode_access_token
from backend.auth.service import (
    ProjectResult,
    get_project,
    get_user,
    list_user_memberships,
    list_user_projects_for_domain,
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user(get_engine(), user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Token refers to a deleted user")
    return CurrentUser(user_id=user.user_id, email=user.email)


@dataclass(frozen=True)
class ProjectContext:
    project: ProjectResult
    role: str
    user: CurrentUser


def get_project_context(
    domain: str,
    project_id: str | None = Query(default=None, description="Required if you belong to more than one project for this domain."),
    user: CurrentUser = Depends(get_current_user),
) -> ProjectContext:
    if domain not in available_domains():
        raise HTTPException(status_code=404, detail=f"Unknown domain '{domain}'. Available: {available_domains()}")

    engine = get_engine()

    if project_id is not None:
        project = get_project(engine, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"No project with id '{project_id}'")
        if project.domain != domain:
            raise HTTPException(status_code=400, detail=f"Project '{project_id}' is a '{project.domain}' project, not '{domain}'")
        memberships = {m.org_id: m.role for m in list_user_memberships(engine, user.user_id)}
        role = memberships.get(project.org_id)
        if role is None:
            raise HTTPException(status_code=403, detail=f"You are not a member of the organization that owns project '{project_id}'")
        return ProjectContext(project=project, role=role, user=user)

    candidates = list_user_projects_for_domain(engine, user.user_id, domain)
    if not candidates:
        raise HTTPException(status_code=403, detail=f"You do not belong to any '{domain}' project")
    if len(candidates) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"You belong to {len(candidates)} '{domain}' projects — pass project_id to disambiguate: {[c.project_id for c in candidates]}",
        )
    project = candidates[0]
    memberships = {m.org_id: m.role for m in list_user_memberships(engine, user.user_id)}
    return ProjectContext(project=project, role=memberships[project.org_id], user=user)


def require_role(minimum: str):
    def _dependency(ctx: ProjectContext = Depends(get_project_context)) -> ProjectContext:
        if ROLE_RANK[ctx.role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail=f"Requires role '{minimum}' or higher in this project's organization; you have '{ctx.role}'")
        return ctx

    return _dependency


def get_project_context_by_id(
    project_id: str = Query(..., description="The project this request scopes to."),
    user: CurrentUser = Depends(get_current_user),
) -> ProjectContext:
    """Same access check as get_project_context, for the handful of
    routes (backend.app.routers.alerts's list endpoint) that aren't
    already keyed by a `domain` path segment and so must take project_id
    directly instead of inferring it."""
    engine = get_engine()
    project = get_project(engine, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No project with id '{project_id}'")
    memberships = {m.org_id: m.role for m in list_user_memberships(engine, user.user_id)}
    role = memberships.get(project.org_id)
    if role is None:
        raise HTTPException(status_code=403, detail=f"You are not a member of the organization that owns project '{project_id}'")
    return ProjectContext(project=project, role=role, user=user)
