"""Centralized RBAC access resolution for projects, research chats, and documents."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.collaboration import CollaboratorRole, higher_role, role_satisfies
from app.models.collaboration import ProjectMember, ResearchMember
from app.models.document import Document
from app.models.project import ResearchProject
from app.models.research import Research
from app.models.user import User


def actor_for_user(session: Session, user_id: UUID | None) -> dict[str, str] | None:
    if user_id is None:
        return None
    row = session.execute(
        select(User.id, User.name, User.email).where(User.id == user_id)
    ).first()
    if row is None:
        return {"userId": str(user_id)}
    return {
        "userId": str(row.id),
        "name": row.name,
        "email": row.email,
    }


def _permission_error(minimum: CollaboratorRole) -> AppError:
    if minimum == CollaboratorRole.OWNER:
        return AppError(
            "Only the project or chat owner can perform this action",
            status_code=403,
            code="owner_required",
        )
    return AppError(
        "Viewers have read-only access and cannot make changes",
        status_code=403,
        code="insufficient_permissions",
    )


def accessible_project_ids_select(
    user_id: UUID,
    *,
    include_archived: bool = True,
):
    """Select project IDs owned by or shared with ``user_id``."""
    member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    conditions = [
        or_(
            ResearchProject.user_id == user_id,
            ResearchProject.id.in_(member_projects),
        )
    ]
    if not include_archived:
        conditions.append(ResearchProject.archived_at.is_(None))
    return select(ResearchProject.id).where(*conditions)


def resolve_project_role(
    session: Session,
    project: ResearchProject,
    user_id: UUID,
) -> CollaboratorRole | None:
    if project.user_id == user_id:
        return CollaboratorRole.OWNER
    raw_role = session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    return CollaboratorRole(raw_role) if raw_role is not None else None


def require_project_access(
    session: Session,
    project_id: UUID,
    user_id: UUID,
    *,
    min_role: CollaboratorRole = CollaboratorRole.VIEWER,
    include_archived: bool = False,
) -> tuple[ResearchProject, CollaboratorRole]:
    filters = [ResearchProject.id == project_id]
    if not include_archived:
        filters.append(ResearchProject.archived_at.is_(None))
    project = session.scalar(select(ResearchProject).where(*filters))
    if project is None:
        raise AppError(
            "Research project not found",
            status_code=404,
            code="research_project_not_found",
        )
    role = resolve_project_role(session, project, user_id)
    if role is None:
        raise AppError(
            "Research project not found",
            status_code=404,
            code="research_project_not_found",
        )
    if not role_satisfies(role, min_role):
        raise _permission_error(min_role)
    return project, role


def resolve_research_role(
    session: Session,
    research_record: Research,
    user_id: UUID,
) -> CollaboratorRole | None:
    resolved: CollaboratorRole | None = None
    if research_record.user_id == user_id:
        resolved = CollaboratorRole.OWNER

    direct_role = session.scalar(
        select(ResearchMember.role).where(
            ResearchMember.research_id == research_record.id,
            ResearchMember.user_id == user_id,
        )
    )
    if direct_role is not None:
        resolved = higher_role(resolved, CollaboratorRole(direct_role))

    if research_record.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(ResearchProject.id == research_record.project_id)
        )
        if project is not None:
            resolved = higher_role(resolved, resolve_project_role(session, project, user_id))

    return resolved


def require_research_access(
    session: Session,
    research_id: UUID,
    user_id: UUID | None,
    *,
    min_role: CollaboratorRole = CollaboratorRole.VIEWER,
    include_archived: bool = False,
) -> tuple[Research, CollaboratorRole]:
    filters = [Research.id == research_id]
    if not include_archived:
        filters.append(Research.archived_at.is_(None))
    record = session.scalar(select(Research).where(*filters))
    if record is None:
        raise AppError(
            "Research not found",
            status_code=404,
            code="research_not_found",
        )
    if user_id is None:
        return record, CollaboratorRole.OWNER
    role = resolve_research_role(session, record, user_id)
    if role is None:
        raise AppError(
            "Research not found",
            status_code=404,
            code="research_not_found",
        )
    if not role_satisfies(role, min_role):
        raise _permission_error(min_role)
    return record, role


def resolve_document_role(
    session: Session,
    document: Document,
    user_id: UUID,
) -> CollaboratorRole | None:
    if document.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(ResearchProject.id == document.project_id)
        )
        if project is not None:
            project_role = resolve_project_role(session, project, user_id)
            if project_role is not None:
                # Uploader of a file inside a shared project can at minimum read/manage
                # according to their project role (viewer stays read-only on project changes).
                return project_role
    if document.user_id == user_id:
        return CollaboratorRole.OWNER
    return None


def require_document_access(
    session: Session,
    document_id: UUID,
    user_id: UUID,
    *,
    min_role: CollaboratorRole = CollaboratorRole.VIEWER,
) -> tuple[Document, CollaboratorRole]:
    document = session.get(Document, document_id)
    if document is None:
        raise AppError(
            "Document not found",
            status_code=404,
            code="document_not_found",
        )
    role = resolve_document_role(session, document, user_id)
    if role is None:
        raise AppError(
            "Document not found",
            status_code=404,
            code="document_not_found",
        )
    if not role_satisfies(role, min_role):
        raise _permission_error(min_role)
    return document, role
