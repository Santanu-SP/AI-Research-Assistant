"""Pydantic request and response schemas for collaboration, invites, and roles."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from app.domain.collaboration import CollaboratorRole, InviteResourceType
from app.schemas.base import ApiSchema

InviteRoleLiteral = Literal["editor", "viewer"]


class CollaboratorMemberResponse(ApiSchema):
    user_id: UUID
    name: str
    email: str
    role: CollaboratorRole
    is_owner: bool = False
    joined_at: datetime


class CollaborationInviteResponse(ApiSchema):
    id: UUID
    resource_type: InviteResourceType
    project_id: UUID | None = None
    research_id: UUID | None = None
    role: InviteRoleLiteral
    target_email: str | None = None
    max_uses: int | None = None
    use_count: int = Field(ge=0)
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    accepted_at: datetime | None = None
    created_at: datetime


class CollaboratorsListResponse(ApiSchema):
    resource_type: InviteResourceType
    resource_id: UUID
    my_role: CollaboratorRole
    version: int = Field(ge=1)
    members: list[CollaboratorMemberResponse]
    invites: list[CollaborationInviteResponse] = Field(default_factory=list)


class EmailInviteCreateRequest(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: str = Field(min_length=3, max_length=320)
    role: InviteRoleLiteral = "editor"

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return cleaned


class EmailInviteResultResponse(ApiSchema):
    member_added: bool
    member: CollaboratorMemberResponse | None = None
    invite: CollaborationInviteResponse
    invite_path: str
    token: str


class LinkInviteCreateRequest(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: InviteRoleLiteral = "editor"
    expires_in_hours: int | None = Field(default=168, ge=1, le=720)
    max_uses: int | None = Field(default=None, ge=1, le=500)


class LinkInviteCreateResponse(ApiSchema):
    invite: CollaborationInviteResponse
    invite_path: str
    token: str


class MemberRoleUpdateRequest(ApiSchema):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: InviteRoleLiteral


class InvitePreviewResponse(ApiSchema):
    resource_type: InviteResourceType
    resource_id: UUID
    resource_title: str
    inviter_name: str | None = None
    role: InviteRoleLiteral
    target_email: str | None = None
    expires_at: datetime | None = None
    already_member: bool = False


class InviteAcceptResponse(ApiSchema):
    resource_type: InviteResourceType
    resource_id: UUID
    role: CollaboratorRole
    redirect_path: str
