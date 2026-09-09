from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class UserSchema(BaseModel):
    user_id: str
    email: str
    created_at: datetime


class MembershipSchema(BaseModel):
    membership_id: str
    org_id: str
    user_id: str
    email: str
    role: Literal["admin", "analyst", "viewer"]
    created_at: datetime


class ProjectSchema(BaseModel):
    project_id: str
    org_id: str
    name: str
    domain: str
    created_at: datetime


class OrganizationSchema(BaseModel):
    org_id: str
    name: str
    created_at: datetime


class CreateOrganizationRequest(BaseModel):
    name: str


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "analyst", "viewer"]


class CreateProjectRequest(BaseModel):
    name: str
    domain: str


class MeResponse(BaseModel):
    user: UserSchema
    memberships: list[MembershipSchema]
    projects: list[ProjectSchema]
