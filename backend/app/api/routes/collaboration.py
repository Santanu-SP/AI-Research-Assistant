"""HTTP endpoints for project/research sharing, role management, and invites."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.domain.collaboration import CollaboratorRole, InviteResourceType
from app.schemas.collaboration import (
    CollaboratorMemberResponse,
    CollaboratorsListResponse,
    EmailInviteCreateRequest,
    EmailInviteResultResponse,
    InviteAcceptResponse,
    InvitePreviewResponse,
    LinkInviteCreateRequest,
    LinkInviteCreateResponse,
    MemberRoleUpdateRequest,
)
from app.services.collaboration import service as collab_service

router = APIRouter(tags=["collaboration"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/projects/{project_id}/members",
    response_model=CollaboratorsListResponse,
)
def list_project_members(
    project_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> CollaboratorsListResponse:
    return collab_service.list_collaborators(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        user_id=user.id,
    )


@router.post(
    "/projects/{project_id}/members",
    response_model=EmailInviteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_project_member_by_email(
    project_id: UUID,
    payload: EmailInviteCreateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> EmailInviteResultResponse:
    return collab_service.invite_by_email(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        user_id=user.id,
        email=payload.email,
        role=CollaboratorRole(payload.role),
    )


@router.patch(
    "/projects/{project_id}/members/{member_user_id}",
    response_model=CollaboratorMemberResponse,
)
def update_project_member_role(
    project_id: UUID,
    member_user_id: UUID,
    payload: MemberRoleUpdateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> CollaboratorMemberResponse:
    return collab_service.update_member_role(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        target_user_id=member_user_id,
        new_role=CollaboratorRole(payload.role),
        actor_user_id=user.id,
    )


@router.delete(
    "/projects/{project_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: UUID,
    member_user_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    collab_service.remove_member(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        target_user_id=member_user_id,
        actor_user_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/invites",
    response_model=LinkInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_invite_link(
    project_id: UUID,
    payload: LinkInviteCreateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> LinkInviteCreateResponse:
    return collab_service.create_invite_link(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        user_id=user.id,
        role=CollaboratorRole(payload.role),
        expires_in_hours=payload.expires_in_hours,
        max_uses=payload.max_uses,
    )


@router.delete(
    "/projects/{project_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_project_invite(
    project_id: UUID,
    invite_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    collab_service.revoke_invite(
        session,
        resource_type=InviteResourceType.PROJECT,
        resource_id=project_id,
        invite_id=invite_id,
        user_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/research/{research_id}/members",
    response_model=CollaboratorsListResponse,
)
def list_research_members(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> CollaboratorsListResponse:
    return collab_service.list_collaborators(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        user_id=user.id,
    )


@router.post(
    "/research/{research_id}/members",
    response_model=EmailInviteResultResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_research_member_by_email(
    research_id: UUID,
    payload: EmailInviteCreateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> EmailInviteResultResponse:
    return collab_service.invite_by_email(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        user_id=user.id,
        email=payload.email,
        role=CollaboratorRole(payload.role),
    )


@router.patch(
    "/research/{research_id}/members/{member_user_id}",
    response_model=CollaboratorMemberResponse,
)
def update_research_member_role(
    research_id: UUID,
    member_user_id: UUID,
    payload: MemberRoleUpdateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> CollaboratorMemberResponse:
    return collab_service.update_member_role(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        target_user_id=member_user_id,
        new_role=CollaboratorRole(payload.role),
        actor_user_id=user.id,
    )


@router.delete(
    "/research/{research_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_research_member(
    research_id: UUID,
    member_user_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    collab_service.remove_member(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        target_user_id=member_user_id,
        actor_user_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/research/{research_id}/invites",
    response_model=LinkInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_invite_link(
    research_id: UUID,
    payload: LinkInviteCreateRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> LinkInviteCreateResponse:
    return collab_service.create_invite_link(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        user_id=user.id,
        role=CollaboratorRole(payload.role),
        expires_in_hours=payload.expires_in_hours,
        max_uses=payload.max_uses,
    )


@router.delete(
    "/research/{research_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_research_invite(
    research_id: UUID,
    invite_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    collab_service.revoke_invite(
        session,
        resource_type=InviteResourceType.RESEARCH,
        resource_id=research_id,
        invite_id=invite_id,
        user_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/collaboration/invites/{token}",
    response_model=InvitePreviewResponse,
)
def preview_collaboration_invite(
    token: str,
    session: DatabaseSession,
    user: CurrentUser,
) -> InvitePreviewResponse:
    return collab_service.preview_invite(session, token=token, user=user)


@router.post(
    "/collaboration/invites/{token}/accept",
    response_model=InviteAcceptResponse,
)
def accept_collaboration_invite(
    token: str,
    session: DatabaseSession,
    user: CurrentUser,
) -> InviteAcceptResponse:
    return collab_service.accept_invite(session, token=token, user=user)
