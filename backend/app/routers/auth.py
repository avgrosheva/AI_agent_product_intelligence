"""Stage 7 tasks 1-3: registration/login, organizations, memberships
(roles), and projects. The only router that issues tokens; every other
router just verifies one via backend.app.auth_deps.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_engine
from backend.app.schemas.auth import (
    AddMemberRequest,
    CreateOrganizationRequest,
    CreateProjectRequest,
    LoginRequest,
    MeResponse,
    MembershipSchema,
    OrganizationSchema,
    ProjectSchema,
    RegisterRequest,
    TokenResponse,
    UserSchema,
)
from backend.auth.models import ROLE_RANK
from backend.auth.service import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    add_member,
    authenticate_user,
    create_organization,
    create_project,
    get_membership,
    get_user,
    list_members,
    list_org_projects,
    list_user_memberships,
    register_user,
)

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/auth/register", response_model=UserSchema, status_code=201)
def register(body: RegisterRequest) -> UserSchema:
    try:
        result = register_user(get_engine(), body.email, body.password)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return UserSchema(**result.__dict__)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    try:
        token = authenticate_user(get_engine(), body.email, body.password)
    except InvalidCredentials:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    engine = get_engine()
    user_result = get_user(engine, user.user_id)
    memberships = list_user_memberships(engine, user.user_id)
    projects = []
    for m in memberships:
        projects.extend(list_org_projects(engine, m.org_id))
    return MeResponse(
        user=UserSchema(**user_result.__dict__),
        memberships=[MembershipSchema(**m.__dict__) for m in memberships],
        projects=[ProjectSchema(**p.__dict__) for p in projects],
    )


@router.post("/orgs", response_model=OrganizationSchema, status_code=201)
def create_org(body: CreateOrganizationRequest, user: CurrentUser = Depends(get_current_user)) -> OrganizationSchema:
    result = create_organization(get_engine(), body.name, user.user_id)
    return OrganizationSchema(**result.__dict__)


def _require_org_role(org_id: str, user: CurrentUser, minimum: str):
    membership = get_membership(get_engine(), org_id, user.user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this organization")
    if ROLE_RANK[membership.role] < ROLE_RANK[minimum]:
        raise HTTPException(status_code=403, detail=f"Requires role '{minimum}' or higher; you have '{membership.role}'")
    return membership


@router.get("/orgs/{org_id}/members", response_model=list[MembershipSchema])
def get_org_members(org_id: str, user: CurrentUser = Depends(get_current_user)) -> list[MembershipSchema]:
    _require_org_role(org_id, user, "viewer")
    return [MembershipSchema(**m.__dict__) for m in list_members(get_engine(), org_id)]


@router.post("/orgs/{org_id}/members", response_model=MembershipSchema, status_code=201)
def add_org_member(org_id: str, body: AddMemberRequest, user: CurrentUser = Depends(get_current_user)) -> MembershipSchema:
    _require_org_role(org_id, user, "admin")
    try:
        result = add_member(get_engine(), org_id, body.email, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return MembershipSchema(**result.__dict__)


@router.get("/orgs/{org_id}/projects", response_model=list[ProjectSchema])
def get_org_projects(org_id: str, user: CurrentUser = Depends(get_current_user)) -> list[ProjectSchema]:
    _require_org_role(org_id, user, "viewer")
    return [ProjectSchema(**p.__dict__) for p in list_org_projects(get_engine(), org_id)]


@router.post("/orgs/{org_id}/projects", response_model=ProjectSchema, status_code=201)
def create_org_project(org_id: str, body: CreateProjectRequest, user: CurrentUser = Depends(get_current_user)) -> ProjectSchema:
    _require_org_role(org_id, user, "admin")
    if body.domain not in available_domains():
        # Stage 8 task 2: reject unknown domains outright — otherwise a
        # typo'd domain silently creates an orphaned project with no
        # adapter, invisible forever except by its raw database row.
        raise HTTPException(status_code=422, detail=f"Unknown domain '{body.domain}'. Available: {available_domains()}")
    result = create_project(get_engine(), org_id, body.name, body.domain)
    return ProjectSchema(**result.__dict__)
