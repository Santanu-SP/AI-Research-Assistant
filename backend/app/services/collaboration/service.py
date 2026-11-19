"""Membership management, email/link invites, and response metadata enrichment."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import secrets
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.realtime_bus import project_room, publish_realtime_event, research_room
from app.core.time import utc_now
from app.domain.collaboration import CollaboratorRole, InviteResourceType, higher_role
from app.models.collaboration import CollaborationInvite, ProjectMember, ResearchMember
from app.models.project import ResearchProject
from app.models.research import Research
from app.models.user import User
from app.schemas.collaboration import (
    CollaborationInviteResponse,
    CollaboratorMemberResponse,
    CollaboratorsListResponse,
    EmailInviteResultResponse,
    InviteAcceptResponse,
    InvitePreviewResponse,
    LinkInviteCreateResponse,
)
from app.services.collaboration.access import (
    actor_for_user,
    require_project_access,
    require_research_access,
)


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _commit(session: Session, message: str = "Could not save collaboration changes") -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(
            message,
            status_code=500,
            code="collaboration_persistence_error",
        ) from exc


def _broadcast_for_resource(
    session: Session,
    resource_type: InviteResourceType,
    resource_id: UUID,
    event_type: str,
    payload: dict[str, object],
    actor_id: UUID | None,
) -> None:
    rooms: list[str] = []
    if resource_type == InviteResourceType.PROJECT:
        rooms.append(project_room(resource_id))
    else:
        rooms.append(research_room(resource_id))
        run = session.get(Research, resource_id)
        if run is not None and run.project_id is not None:
            rooms.append(project_room(run.project_id))
    publish_realtime_event(
        rooms,
        event_type,
        payload,
        actor=actor_for_user(session, actor_id),
    )


def _serialize_invite(invite: CollaborationInvite) -> CollaborationInviteResponse:
    return CollaborationInviteResponse(
        id=invite.id,
        resource_type=InviteResourceType(invite.resource_type),
        project_id=invite.project_id,
        research_id=invite.research_id,
        role=invite.role,  # type: ignore[arg-type]
        target_email=invite.target_email,
        max_uses=invite.max_uses,
        use_count=invite.use_count,
        expires_at=invite.expires_at,
        revoked_at=invite.revoked_at,
        accepted_at=invite.accepted_at,
        created_at=invite.created_at,
    )


def _load_resource_and_role(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    user_id: UUID,
    min_role: CollaboratorRole,
) -> tuple[ResearchProject | Research, CollaboratorRole]:
    if resource_type == InviteResourceType.PROJECT:
        return require_project_access(session, resource_id, user_id, min_role=min_role)
    return require_research_access(session, resource_id, user_id, min_role=min_role)


def _upsert_project_member(
    session: Session,
    *,
    project_id: UUID,
    owner_user_id: UUID,
    member_user_id: UUID,
    role: CollaboratorRole,
    invited_by_id: UUID | None,
) -> CollaboratorMemberResponse:
    if member_user_id == owner_user_id:
        user = session.get(User, owner_user_id)
        assert user is not None
        return CollaboratorMemberResponse(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=CollaboratorRole.OWNER,
            is_owner=True,
            joined_at=utc_now(),
        )

    existing = session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_user_id,
        )
    )
    if existing is None:
        existing = ProjectMember(
            project_id=project_id,
            user_id=member_user_id,
            role=role.value,
            invited_by_id=invited_by_id,
        )
        session.add(existing)
    else:
        existing.role = role.value
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == member_user_id,
            )
        )
        if existing is None:
            raise
        existing.role = role.value
        session.commit()
    session.refresh(existing)
    user = session.get(User, member_user_id)
    assert user is not None
    return CollaboratorMemberResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=CollaboratorRole(existing.role),
        is_owner=False,
        joined_at=existing.created_at,
    )


def _upsert_research_member(
    session: Session,
    *,
    research_id: UUID,
    owner_user_id: UUID | None,
    member_user_id: UUID,
    role: CollaboratorRole,
    invited_by_id: UUID | None,
) -> CollaboratorMemberResponse:
    if owner_user_id is not None and member_user_id == owner_user_id:
        user = session.get(User, owner_user_id)
        assert user is not None
        return CollaboratorMemberResponse(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=CollaboratorRole.OWNER,
            is_owner=True,
            joined_at=utc_now(),
        )

    existing = session.scalar(
        select(ResearchMember).where(
            ResearchMember.research_id == research_id,
            ResearchMember.user_id == member_user_id,
        )
    )
    if existing is None:
        existing = ResearchMember(
            research_id=research_id,
            user_id=member_user_id,
            role=role.value,
            invited_by_id=invited_by_id,
        )
        session.add(existing)
    else:
        existing.role = role.value
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ResearchMember).where(
                ResearchMember.research_id == research_id,
                ResearchMember.user_id == member_user_id,
            )
        )
        if existing is None:
            raise
        existing.role = role.value
        session.commit()
    session.refresh(existing)
    user = session.get(User, member_user_id)
    assert user is not None
    return CollaboratorMemberResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=CollaboratorRole(existing.role),
        is_owner=False,
        joined_at=existing.created_at,
    )


def list_collaborators(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    user_id: UUID,
) -> CollaboratorsListResponse:
    resource, my_role = _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        min_role=CollaboratorRole.VIEWER,
    )

    members: list[CollaboratorMemberResponse] = []
    seen_users: set[UUID] = set()

    if resource.user_id is not None:
        owner = session.get(User, resource.user_id)
        if owner is not None:
            seen_users.add(owner.id)
            members.append(
                CollaboratorMemberResponse(
                    user_id=owner.id,
                    name=owner.name,
                    email=owner.email,
                    role=CollaboratorRole.OWNER,
                    is_owner=True,
                    joined_at=resource.created_at,
                )
            )

    if resource_type == InviteResourceType.PROJECT:
        rows = session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == resource_id)
            .order_by(ProjectMember.created_at.asc())
        ).all()
        for pm, u in rows:
            if u.id in seen_users:
                continue
            seen_users.add(u.id)
            members.append(
                CollaboratorMemberResponse(
                    user_id=u.id,
                    name=u.name,
                    email=u.email,
                    role=CollaboratorRole(pm.role),
                    is_owner=False,
                    joined_at=pm.created_at,
                )
            )
    else:
        assert isinstance(resource, Research)
        rows = session.execute(
            select(ResearchMember, User)
            .join(User, User.id == ResearchMember.user_id)
            .where(ResearchMember.research_id == resource_id)
            .order_by(ResearchMember.created_at.asc())
        ).all()
        for rm, u in rows:
            if u.id in seen_users:
                continue
            seen_users.add(u.id)
            members.append(
                CollaboratorMemberResponse(
                    user_id=u.id,
                    name=u.name,
                    email=u.email,
                    role=CollaboratorRole(rm.role),
                    is_owner=False,
                    joined_at=rm.created_at,
                )
            )
        if resource.project_id is not None:
            proj = session.get(ResearchProject, resource.project_id)
            if proj is not None and proj.user_id not in seen_users:
                proj_owner = session.get(User, proj.user_id)
                if proj_owner is not None:
                    seen_users.add(proj_owner.id)
                    members.append(
                        CollaboratorMemberResponse(
                            user_id=proj_owner.id,
                            name=proj_owner.name,
                            email=proj_owner.email,
                            role=CollaboratorRole.OWNER,
                            is_owner=True,
                            joined_at=proj.created_at,
                        )
                    )
            proj_rows = session.execute(
                select(ProjectMember, User)
                .join(User, User.id == ProjectMember.user_id)
                .where(ProjectMember.project_id == resource.project_id)
                .order_by(ProjectMember.created_at.asc())
            ).all()
            for pm, u in proj_rows:
                if u.id in seen_users:
                    continue
                seen_users.add(u.id)
                members.append(
                    CollaboratorMemberResponse(
                        user_id=u.id,
                        name=u.name,
                        email=u.email,
                        role=CollaboratorRole(pm.role),
                        is_owner=False,
                        joined_at=pm.created_at,
                    )
                )

    invites: list[CollaborationInviteResponse] = []
    if my_role == CollaboratorRole.OWNER:
        now = utc_now()
        filter_col = (
            CollaborationInvite.project_id
            if resource_type == InviteResourceType.PROJECT
            else CollaborationInvite.research_id
        )
        invite_rows = list(
            session.scalars(
                select(CollaborationInvite)
                .where(
                    CollaborationInvite.resource_type == resource_type.value,
                    filter_col == resource_id,
                    CollaborationInvite.revoked_at.is_(None),
                    or_(
                        CollaborationInvite.expires_at.is_(None),
                        CollaborationInvite.expires_at > now,
                    ),
                )
                .order_by(CollaborationInvite.created_at.desc())
            ).all()
        )
        invites = [_serialize_invite(row) for row in invite_rows]

    return CollaboratorsListResponse(
        resource_type=resource_type,
        resource_id=resource_id,
        my_role=my_role,
        version=getattr(resource, "version", 1),
        members=members,
        invites=invites,
    )


def invite_by_email(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    user_id: UUID,
    email: str,
    role: CollaboratorRole,
) -> EmailInviteResultResponse:
    if role == CollaboratorRole.OWNER:
        raise AppError("Cannot invite directly as owner", status_code=422, code="invalid_role")
    resource, _ = _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        min_role=CollaboratorRole.OWNER,
    )
    normalized_email = email.strip().lower()
    target_user = session.scalar(
        select(User).where(func.lower(User.email) == normalized_email, User.is_active.is_(True))
    )
    if target_user is not None and resource.user_id == target_user.id:
        raise AppError(
            "This user is already the owner",
            status_code=409,
            code="already_resource_owner",
        )

    token = secrets.token_urlsafe(32)
    now = utc_now()
    invite = CollaborationInvite(
        resource_type=resource_type.value,
        project_id=resource_id if resource_type == InviteResourceType.PROJECT else None,
        research_id=resource_id if resource_type == InviteResourceType.RESEARCH else None,
        role=role.value,
        target_email=normalized_email,
        token_hash=_hash_token(token),
        created_by_id=user_id,
        max_uses=1,
        use_count=1 if target_user is not None else 0,
        expires_at=now + timedelta(days=7),
        accepted_at=now if target_user is not None else None,
    )
    session.add(invite)
    _commit(session, "Could not create email invite")
    session.refresh(invite)

    member: CollaboratorMemberResponse | None = None
    if target_user is not None:
        if resource_type == InviteResourceType.PROJECT:
            member = _upsert_project_member(
                session,
                project_id=resource_id,
                owner_user_id=resource.user_id,
                member_user_id=target_user.id,
                role=role,
                invited_by_id=user_id,
            )
        else:
            member = _upsert_research_member(
                session,
                research_id=resource_id,
                owner_user_id=resource.user_id,
                member_user_id=target_user.id,
                role=role,
                invited_by_id=user_id,
            )
        _broadcast_for_resource(
            session,
            resource_type,
            resource_id,
            "member.joined",
            {
                "resourceType": resource_type.value,
                "resourceId": str(resource_id),
                "member": member.model_dump(by_alias=True, mode="json"),
            },
            user_id,
        )

    return EmailInviteResultResponse(
        member_added=member is not None,
        member=member,
        invite=_serialize_invite(invite),
        invite_path=f"/join/{token}",
        token=token,
    )


def create_invite_link(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    user_id: UUID,
    role: CollaboratorRole,
    expires_in_hours: int | None = 168,
    max_uses: int | None = None,
) -> LinkInviteCreateResponse:
    if role == CollaboratorRole.OWNER:
        raise AppError("Cannot issue an owner invite link", status_code=422, code="invalid_role")
    _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        min_role=CollaboratorRole.OWNER,
    )
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=expires_in_hours) if expires_in_hours else None
    invite = CollaborationInvite(
        resource_type=resource_type.value,
        project_id=resource_id if resource_type == InviteResourceType.PROJECT else None,
        research_id=resource_id if resource_type == InviteResourceType.RESEARCH else None,
        role=role.value,
        target_email=None,
        token_hash=_hash_token(token),
        created_by_id=user_id,
        max_uses=max_uses,
        use_count=0,
        expires_at=expires_at,
    )
    session.add(invite)
    _commit(session, "Could not create invite link")
    session.refresh(invite)
    return LinkInviteCreateResponse(
        invite=_serialize_invite(invite),
        invite_path=f"/join/{token}",
        token=token,
    )


def revoke_invite(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    invite_id: UUID,
    user_id: UUID,
) -> None:
    _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        min_role=CollaboratorRole.OWNER,
    )
    invite = session.get(CollaborationInvite, invite_id)
    matches_resource = (
        invite is not None
        and invite.resource_type == resource_type.value
        and (
            (resource_type == InviteResourceType.PROJECT and invite.project_id == resource_id)
            or (resource_type == InviteResourceType.RESEARCH and invite.research_id == resource_id)
        )
    )
    if not matches_resource:
        raise AppError("Invite not found", status_code=404, code="invite_not_found")
    assert invite is not None
    invite.revoked_at = utc_now()
    _commit(session, "Could not revoke invite")


def update_member_role(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    target_user_id: UUID,
    new_role: CollaboratorRole,
    actor_user_id: UUID,
) -> CollaboratorMemberResponse:
    if new_role == CollaboratorRole.OWNER:
        raise AppError("Ownership cannot be reassigned here", status_code=422, code="invalid_role")
    resource, _ = _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=actor_user_id,
        min_role=CollaboratorRole.OWNER,
    )
    if resource.user_id == target_user_id:
        raise AppError("Owner role cannot be changed", status_code=409, code="cannot_modify_owner")

    if resource_type == InviteResourceType.PROJECT:
        member_row = session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == resource_id,
                ProjectMember.user_id == target_user_id,
            )
        )
    else:
        member_row = session.scalar(
            select(ResearchMember).where(
                ResearchMember.research_id == resource_id,
                ResearchMember.user_id == target_user_id,
            )
        )
    if member_row is None:
        raise AppError("Collaborator not found", status_code=404, code="member_not_found")

    member_row.role = new_role.value
    _commit(session, "Could not update collaborator role")
    session.refresh(member_row)
    target_user = session.get(User, target_user_id)
    assert target_user is not None
    updated = CollaboratorMemberResponse(
        user_id=target_user.id,
        name=target_user.name,
        email=target_user.email,
        role=CollaboratorRole(member_row.role),
        is_owner=False,
        joined_at=member_row.created_at,
    )
    _broadcast_for_resource(
        session,
        resource_type,
        resource_id,
        "member.updated",
        {
            "resourceType": resource_type.value,
            "resourceId": str(resource_id),
            "member": updated.model_dump(by_alias=True, mode="json"),
        },
        actor_user_id,
    )
    return updated


def remove_member(
    session: Session,
    *,
    resource_type: InviteResourceType,
    resource_id: UUID,
    target_user_id: UUID,
    actor_user_id: UUID,
) -> None:
    is_self_leave = target_user_id == actor_user_id
    resource, _ = _load_resource_and_role(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=actor_user_id,
        min_role=CollaboratorRole.VIEWER if is_self_leave else CollaboratorRole.OWNER,
    )
    if resource.user_id == target_user_id:
        raise AppError(
            "The owner cannot be removed from their own workspace",
            status_code=409,
            code="cannot_remove_owner",
        )

    if resource_type == InviteResourceType.PROJECT:
        member_row = session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == resource_id,
                ProjectMember.user_id == target_user_id,
            )
        )
    else:
        member_row = session.scalar(
            select(ResearchMember).where(
                ResearchMember.research_id == resource_id,
                ResearchMember.user_id == target_user_id,
            )
        )
    if member_row is None:
        raise AppError("Collaborator not found", status_code=404, code="member_not_found")

    session.delete(member_row)
    _commit(session, "Could not remove collaborator")
    _broadcast_for_resource(
        session,
        resource_type,
        resource_id,
        "member.removed",
        {
            "resourceType": resource_type.value,
            "resourceId": str(resource_id),
            "userId": str(target_user_id),
        },
        actor_user_id,
    )


def _validate_invite_token(session: Session, token: str) -> CollaborationInvite:
    cleaned = token.strip()
    if not cleaned:
        raise AppError("Invite link is invalid", status_code=404, code="invite_not_found")
    invite = session.scalar(
        select(CollaborationInvite).where(CollaborationInvite.token_hash == _hash_token(cleaned))
    )
    if invite is None:
        raise AppError("Invite link is invalid", status_code=404, code="invite_not_found")
    now = utc_now()
    if invite.revoked_at is not None:
        raise AppError("This invite link has been revoked", status_code=410, code="invite_revoked")
    if invite.expires_at is not None and invite.expires_at <= now:
        raise AppError("This invite link has expired", status_code=410, code="invite_expired")
    if invite.max_uses is not None and invite.use_count >= invite.max_uses:
        raise AppError(
            "This invite link has already reached its usage limit",
            status_code=410,
            code="invite_exhausted",
        )
    return invite


def preview_invite(
    session: Session,
    *,
    token: str,
    user: User,
) -> InvitePreviewResponse:
    invite = _validate_invite_token(session, token)
    if invite.target_email and invite.target_email.lower() != user.email.lower():
        raise AppError(
            "This invite was sent to a different email address",
            status_code=403,
            code="invite_email_mismatch",
        )

    inviter = session.get(User, invite.created_by_id) if invite.created_by_id else None
    already_member = False
    resource_title = "Shared workspace"
    resource_id: UUID

    if invite.resource_type == InviteResourceType.PROJECT.value and invite.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == invite.project_id,
                ResearchProject.archived_at.is_(None),
            )
        )
        if project is None:
            raise AppError("Project is no longer available", status_code=404, code="invite_not_found")
        resource_id = project.id
        resource_title = project.name
        already_member = (
            project.user_id == user.id
            or session.scalar(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == user.id,
                )
            )
            is not None
        )
    elif invite.research_id is not None:
        run = session.scalar(
            select(Research).where(
                Research.id == invite.research_id,
                Research.archived_at.is_(None),
            )
        )
        if run is None:
            raise AppError("Research chat is no longer available", status_code=404, code="invite_not_found")
        resource_id = run.id
        resource_title = run.title
        already_member = (
            run.user_id == user.id
            or session.scalar(
                select(ResearchMember.id).where(
                    ResearchMember.research_id == run.id,
                    ResearchMember.user_id == user.id,
                )
            )
            is not None
        )
    else:
        raise AppError("Invite target missing", status_code=404, code="invite_not_found")

    return InvitePreviewResponse(
        resource_type=InviteResourceType(invite.resource_type),
        resource_id=resource_id,
        resource_title=resource_title,
        inviter_name=inviter.name if inviter else None,
        role=invite.role,  # type: ignore[arg-type]
        target_email=invite.target_email,
        expires_at=invite.expires_at,
        already_member=already_member,
    )


def accept_invite(
    session: Session,
    *,
    token: str,
    user: User,
) -> InviteAcceptResponse:
    invite = _validate_invite_token(session, token)
    if invite.target_email and invite.target_email.lower() != user.email.lower():
        raise AppError(
            "This invite was sent to a different email address",
            status_code=403,
            code="invite_email_mismatch",
        )

    now = utc_now()
    invite_role = CollaboratorRole(invite.role)

    if invite.resource_type == InviteResourceType.PROJECT.value and invite.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == invite.project_id,
                ResearchProject.archived_at.is_(None),
            )
        )
        if project is None:
            raise AppError("Project is no longer available", status_code=404, code="invite_not_found")

        existing = session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
        if project.user_id == user.id:
            return InviteAcceptResponse(
                resource_type=InviteResourceType.PROJECT,
                resource_id=project.id,
                role=CollaboratorRole.OWNER,
                redirect_path=f"/projects/{project.id}",
            )

        # Atomic use-count reservation avoids oversubscribing a max_uses invite under races.
        claim_conditions = [
            CollaborationInvite.id == invite.id,
            CollaborationInvite.revoked_at.is_(None),
        ]
        if invite.max_uses is not None:
            claim_conditions.append(CollaborationInvite.use_count < invite.max_uses)
        claimed = session.execute(
            update(CollaborationInvite)
            .where(*claim_conditions)
            .values(
                use_count=CollaborationInvite.use_count + 1,
                accepted_at=now,
            )
        )
        if claimed.rowcount == 0:
            session.rollback()
            raise AppError(
                "This invite link has already reached its usage limit",
                status_code=410,
                code="invite_exhausted",
            )
        effective_role = (
            higher_role(CollaboratorRole(existing.role), invite_role) or invite_role
            if existing is not None
            else invite_role
        )
        member = _upsert_project_member(
            session,
            project_id=project.id,
            owner_user_id=project.user_id,
            member_user_id=user.id,
            role=effective_role,
            invited_by_id=invite.created_by_id,
        )
        _broadcast_for_resource(
            session,
            InviteResourceType.PROJECT,
            project.id,
            "member.joined",
            {
                "resourceType": InviteResourceType.PROJECT.value,
                "resourceId": str(project.id),
                "member": member.model_dump(by_alias=True, mode="json"),
            },
            user.id,
        )
        return InviteAcceptResponse(
            resource_type=InviteResourceType.PROJECT,
            resource_id=project.id,
            role=effective_role,
            redirect_path=f"/projects/{project.id}",
        )

    if invite.research_id is not None:
        run = session.scalar(
            select(Research).where(
                Research.id == invite.research_id,
                Research.archived_at.is_(None),
            )
        )
        if run is None:
            raise AppError("Research chat is no longer available", status_code=404, code="invite_not_found")
        if run.user_id == user.id:
            redirect_path = (
                f"/research/{run.id}" if str(run.status.value) == "completed" else f"/research/{run.id}/progress"
            )
            return InviteAcceptResponse(
                resource_type=InviteResourceType.RESEARCH,
                resource_id=run.id,
                role=CollaboratorRole.OWNER,
                redirect_path=redirect_path,
            )

        existing = session.scalar(
            select(ResearchMember).where(
                ResearchMember.research_id == run.id,
                ResearchMember.user_id == user.id,
            )
        )
        claim_conditions = [
            CollaborationInvite.id == invite.id,
            CollaborationInvite.revoked_at.is_(None),
        ]
        if invite.max_uses is not None:
            claim_conditions.append(CollaborationInvite.use_count < invite.max_uses)
        claimed = session.execute(
            update(CollaborationInvite)
            .where(*claim_conditions)
            .values(
                use_count=CollaborationInvite.use_count + 1,
                accepted_at=now,
            )
        )
        if claimed.rowcount == 0:
            session.rollback()
            raise AppError(
                "This invite link has already reached its usage limit",
                status_code=410,
                code="invite_exhausted",
            )
        effective_role = (
            higher_role(CollaboratorRole(existing.role), invite_role) or invite_role
            if existing is not None
            else invite_role
        )
        member = _upsert_research_member(
            session,
            research_id=run.id,
            owner_user_id=run.user_id,
            member_user_id=user.id,
            role=effective_role,
            invited_by_id=invite.created_by_id,
        )
        _broadcast_for_resource(
            session,
            InviteResourceType.RESEARCH,
            run.id,
            "member.joined",
            {
                "resourceType": InviteResourceType.RESEARCH.value,
                "resourceId": str(run.id),
                "member": member.model_dump(by_alias=True, mode="json"),
            },
            user.id,
        )
        redirect_path = (
            f"/research/{run.id}" if str(run.status.value) == "completed" else f"/research/{run.id}/progress"
        )
        return InviteAcceptResponse(
            resource_type=InviteResourceType.RESEARCH,
            resource_id=run.id,
            role=effective_role,
            redirect_path=redirect_path,
        )

    raise AppError("Invite target missing", status_code=404, code="invite_not_found")


def attach_project_collab_metadata(
    session: Session,
    projects: list[ResearchProject],
    user_id: UUID,
) -> list[ResearchProject]:
    """Attach ``my_role``, ``is_shared``, ``member_count``, and ``owner_name`` without extra GROUP BYs."""
    if not projects:
        return projects
    project_ids = [p.id for p in projects]
    owner_ids = {p.user_id for p in projects}
    owner_names: dict[UUID, str] = {}
    if owner_ids:
        owner_names = dict(
            session.execute(
                select(User.id, User.name).where(User.id.in_(owner_ids))
            ).all()
        )
    member_rows = session.execute(
        select(ProjectMember.project_id, ProjectMember.user_id, ProjectMember.role).where(
            ProjectMember.project_id.in_(project_ids)
        )
    ).all()
    members_by_project: dict[UUID, dict[UUID, CollaboratorRole]] = {}
    for proj_id, mem_user_id, role_str in member_rows:
        members_by_project.setdefault(proj_id, {})[mem_user_id] = CollaboratorRole(role_str)

    for project in projects:
        mem_map = members_by_project.get(project.id, {})
        other_members = {uid: r for uid, r in mem_map.items() if uid != project.user_id}
        member_count = 1 + len(other_members)
        if project.user_id == user_id:
            my_role = CollaboratorRole.OWNER
        else:
            my_role = mem_map.get(user_id, CollaboratorRole.VIEWER)
        project.my_role = my_role  # type: ignore[attr-defined]
        project.is_shared = member_count > 1 or project.user_id != user_id  # type: ignore[attr-defined]
        project.member_count = member_count  # type: ignore[attr-defined]
        project.owner_name = owner_names.get(project.user_id)  # type: ignore[attr-defined]
    return projects


def attach_research_collab_metadata(
    session: Session,
    records: list[Research],
    user_id: UUID | None,
) -> list[Research]:
    """Attach ``my_role``, ``is_shared``, ``member_count``, and ``owner_name`` on research items."""
    if not records:
        return records
    research_ids = [r.id for r in records]
    project_ids = {r.project_id for r in records if r.project_id is not None}
    owner_ids = {r.user_id for r in records if r.user_id is not None}

    proj_owners: dict[UUID, UUID] = {}
    if project_ids:
        for pid, p_owner in session.execute(
            select(ResearchProject.id, ResearchProject.user_id).where(
                ResearchProject.id.in_(project_ids)
            )
        ).all():
            proj_owners[pid] = p_owner
            owner_ids.add(p_owner)

    owner_names: dict[UUID, str] = {}
    if owner_ids:
        owner_names = dict(
            session.execute(
                select(User.id, User.name).where(User.id.in_(owner_ids))
            ).all()
        )

    direct_rows = session.execute(
        select(ResearchMember.research_id, ResearchMember.user_id, ResearchMember.role).where(
            ResearchMember.research_id.in_(research_ids)
        )
    ).all()
    direct_by_research: dict[UUID, dict[UUID, CollaboratorRole]] = {}
    for rid, uid, role_str in direct_rows:
        direct_by_research.setdefault(rid, {})[uid] = CollaboratorRole(role_str)

    proj_members_by_project: dict[UUID, dict[UUID, CollaboratorRole]] = {}
    if project_ids:
        for pid, uid, role_str in session.execute(
            select(ProjectMember.project_id, ProjectMember.user_id, ProjectMember.role).where(
                ProjectMember.project_id.in_(project_ids)
            )
        ).all():
            proj_members_by_project.setdefault(pid, {})[uid] = CollaboratorRole(role_str)

    for rec in records:
        participants: dict[UUID, CollaboratorRole] = {}
        if rec.user_id is not None:
            participants[rec.user_id] = CollaboratorRole.OWNER
        for uid, role in direct_by_research.get(rec.id, {}).items():
            participants[uid] = higher_role(participants.get(uid), role) or role
        if rec.project_id is not None:
            p_owner = proj_owners.get(rec.project_id)
            if p_owner is not None:
                participants[p_owner] = CollaboratorRole.OWNER
            for uid, role in proj_members_by_project.get(rec.project_id, {}).items():
                participants[uid] = higher_role(participants.get(uid), role) or role

        member_count = max(1, len(participants))
        if user_id is None:
            my_role = CollaboratorRole.OWNER
        else:
            my_role = participants.get(user_id, CollaboratorRole.VIEWER)
        is_shared = member_count > 1 or (
            user_id is not None and rec.user_id is not None and rec.user_id != user_id
        )
        rec.my_role = my_role  # type: ignore[attr-defined]
        rec.is_shared = is_shared  # type: ignore[attr-defined]
        rec.member_count = member_count  # type: ignore[attr-defined]
        rec.owner_name = owner_names.get(rec.user_id) if rec.user_id else None  # type: ignore[attr-defined]
    return records
