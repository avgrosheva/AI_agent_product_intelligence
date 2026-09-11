"""Stage 7 tasks 1-3: registration/login, organizations, memberships
(roles), and projects. The only router that issues tokens; every other
router just verifies one via backend.app.auth_deps.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth_deps import CurrentUser, get_current_user
from backend.app.domain_registry import available_domains, get_engine
from backend.audit.service import record_audit_event
from backend.app.schemas.auth import (
    AddMemberRequest,
    CreateOrganizationRequest,
    CreateProjectRequest,
    LoginRequest,
    LogoutAllResponse,
    LogoutRequest,
    MeResponse,
    MembershipSchema,
    OrganizationSchema,
    ProjectSchema,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserSchema,
)
from backend.auth.models import ROLE_RANK
from backend.auth.service import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
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
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
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
        pair = authenticate_user(get_engine(), body.email, body.password)
    except InvalidCredentials:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest) -> TokenResponse:
    """Stage 18 task 4: exchanges one refresh token for a fresh
    (access_token, refresh_token) pair, rotating the old one out —
    presenting the SAME refresh token twice (it was already consumed) is
    indistinguishable from presenting an unknown one, both 401."""
    try:
        pair = rotate_refresh_token(get_engine(), body.refresh_token)
    except InvalidRefreshToken:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/auth/logout", status_code=204)
def logout(body: LogoutRequest) -> None:
    """Ends ONE session: revokes exactly the refresh token presented.
    Never errors on an already-invalid token — logging out twice, or
    logging out a session that already expired, is a no-op success, not
    a failure the caller needs to handle specially."""
    revoke_refresh_token(get_engine(), body.refresh_token)


@router.post("/auth/logout-all", response_model=LogoutAllResponse)
def logout_all(user: CurrentUser = Depends(get_current_user)) -> LogoutAllResponse:
    """"Log out everywhere": revokes every still-valid refresh token
    belonging to the CALLER (identified by their own access token, not a
    target — there is no separate admin-revokes-another-user's-sessions
    endpoint yet, matching the Stage 18 brief's "minimal" scope)."""
    count = revoke_all_refresh_tokens(get_engine(), user.user_id)
    return LogoutAllResponse(revoked_count=count)


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
    record_audit_event(
        get_engine(), action="org_member.add_or_update", actor_user_id=user.user_id, actor_email=user.email,
        org_id=org_id, target=result.email, metadata={"role": result.role},
    )
    return MembershipSchema(**result.__dict__)


@router.post("/orgs/{org_id}/members/{target_user_id}/revoke-sessions", response_model=LogoutAllResponse)
def revoke_member_sessions(org_id: str, target_user_id: str, user: CurrentUser = Depends(get_current_user)) -> LogoutAllResponse:
    """Stage 18 task 4's "admin action" variant of logout-all — an org
    admin forcing a DIFFERENT member's sessions to end (an offboarding, a
    suspected compromised account), scoped to members of the admin's own
    organization only."""
    _require_org_role(org_id, user, "admin")
    engine = get_engine()
    target_membership = get_membership(engine, org_id, target_user_id)
    if target_membership is None:
        raise HTTPException(status_code=404, detail="No member with that user id in this organization")
    count = revoke_all_refresh_tokens(engine, target_user_id)
    record_audit_event(
        engine, action="user_sessions.revoke_all", actor_user_id=user.user_id, actor_email=user.email,
        org_id=org_id, target=target_membership.email, metadata={"revoked_count": count},
    )
    return LogoutAllResponse(revoked_count=count)


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
    record_audit_event(
        get_engine(), action="project.create", actor_user_id=user.user_id, actor_email=user.email,
        org_id=org_id, project_id=result.project_id, target=result.name, metadata={"domain": result.domain},
    )
    return ProjectSchema(**result.__dict__)
