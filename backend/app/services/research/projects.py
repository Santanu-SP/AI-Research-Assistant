from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.realtime_bus import project_room, publish_realtime_event
from app.core.time import utc_now
from app.domain.collaboration import CollaboratorRole
from app.domain.research import ResearchStatus
from app.models.collaboration import ProjectMember
from app.models.document import Document
from app.models.project import ResearchProject
from app.models.research import Research
from app.schemas.projects import ResearchProjectCreate, ResearchProjectUpdate
from app.services.collaboration.access import actor_for_user, require_project_access
from app.services.collaboration.service import attach_project_collab_metadata


def _commit(session: Session) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(
            "The research project could not be saved",
            status_code=500,
            code="research_project_persistence_error",
        ) from exc


def create_project(
    session: Session,
    payload: ResearchProjectCreate,
    user_id: UUID,
) -> ResearchProject:
    project = ResearchProject(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(project)
    _commit(session)
    session.refresh(project)
    attach_project_collab_metadata(session, [project], user_id)
    return project


def list_projects(
    session: Session,
    user_id: UUID,
    *,
    search: str | None,
    limit: int,
    offset: int,
    include_archived: bool,
) -> tuple[list[ResearchProject], int]:
    member_project_ids = select(ProjectMember.project_id).where(
        ProjectMember.user_id == user_id
    )
    filters = [
        or_(
            ResearchProject.user_id == user_id,
            ResearchProject.id.in_(member_project_ids),
        )
    ]
    if not include_archived:
        filters.append(ResearchProject.archived_at.is_(None))
    normalized_search = search.strip() if search else None
    if normalized_search:
        filters.append(
            or_(
                ResearchProject.name.icontains(normalized_search, autoescape=True),
                ResearchProject.description.icontains(
                    normalized_search, autoescape=True
                ),
            )
        )

    total = session.scalar(
        select(func.count()).select_from(ResearchProject).where(*filters)
    )
    items = list(
        session.scalars(
            select(ResearchProject)
            .where(*filters)
            .order_by(ResearchProject.updated_at.desc(), ResearchProject.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    attach_project_counts(session, items)
    attach_project_collab_metadata(session, items, user_id)
    return items, total or 0


def attach_project_counts(
    session: Session, projects: list[ResearchProject]
) -> None:
    """Set ``file_count`` and ``report_count`` on each project.

    Uses one grouped query per count for the whole page instead of a query
    per project.
    """
    if not projects:
        return
    project_ids = [project.id for project in projects]
    file_counts = dict(
        session.execute(
            select(Document.project_id, func.count(Document.id))
            .where(Document.project_id.in_(project_ids))
            .group_by(Document.project_id)
        ).all()
    )
    report_counts = dict(
        session.execute(
            select(Research.project_id, func.count(Research.id))
            .where(
                Research.project_id.in_(project_ids),
                Research.status == ResearchStatus.COMPLETED,
                Research.archived_at.is_(None),
            )
            .group_by(Research.project_id)
        ).all()
    )
    for project in projects:
        project.file_count = int(file_counts.get(project.id, 0))
        project.report_count = int(report_counts.get(project.id, 0))


def get_project(
    session: Session,
    project_id: UUID,
    user_id: UUID,
    *,
    min_role: CollaboratorRole = CollaboratorRole.VIEWER,
    include_archived: bool = False,
) -> ResearchProject:
    project, _ = require_project_access(
        session,
        project_id,
        user_id,
        min_role=min_role,
        include_archived=include_archived,
    )
    return project


def update_project(
    session: Session,
    project_id: UUID,
    payload: ResearchProjectUpdate,
    user_id: UUID,
) -> ResearchProject:
    project = get_project(
        session, project_id, user_id, min_role=CollaboratorRole.EDITOR
    )
    if payload.version is not None and payload.version != project.version:
        raise AppError(
            "This project was updated by a collaborator. Refresh to get the latest changes.",
            status_code=409,
            code="version_conflict",
            details={
                "currentVersion": project.version,
                "name": project.name,
                "description": project.description,
            },
        )
    for field, value in payload.model_dump(exclude_unset=True, exclude={"version"}).items():
        setattr(project, field, value)
    project.version += 1
    project.updated_at = utc_now()
    _commit(session)
    session.refresh(project)
    attach_project_collab_metadata(session, [project], user_id)
    publish_realtime_event(
        [project_room(project.id)],
        "project.updated",
        {
            "projectId": str(project.id),
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "updatedAt": project.updated_at.isoformat(),
        },
        actor=actor_for_user(session, user_id),
    )
    return project


def archive_project(session: Session, project_id: UUID, user_id: UUID) -> None:
    project = get_project(
        session, project_id, user_id, min_role=CollaboratorRole.OWNER
    )
    timestamp = utc_now()
    project.archived_at = timestamp
    project.version += 1
    project.updated_at = timestamp
    _commit(session)
    publish_realtime_event(
        [project_room(project.id)],
        "project.archived",
        {"projectId": str(project.id), "archivedAt": timestamp.isoformat()},
        actor=actor_for_user(session, user_id),
    )


def _get_archived_project(
    session: Session, project_id: UUID, user_id: UUID
) -> ResearchProject:
    project = get_project(
        session,
        project_id,
        user_id,
        min_role=CollaboratorRole.OWNER,
        include_archived=True,
    )
    if project.archived_at is None:
        raise AppError(
            "Only archived projects can be restored or deleted",
            status_code=409,
            code="research_project_not_archived",
        )
    return project


def restore_project(
    session: Session, project_id: UUID, user_id: UUID
) -> ResearchProject:
    project = _get_archived_project(session, project_id, user_id)
    project.archived_at = None
    project.version += 1
    project.updated_at = utc_now()
    _commit(session)
    session.refresh(project)
    attach_project_collab_metadata(session, [project], user_id)
    publish_realtime_event(
        [project_room(project.id)],
        "project.restored",
        {"projectId": str(project.id)},
        actor=actor_for_user(session, user_id),
    )
    return project


def delete_project_permanently(
    session: Session, project_id: UUID, user_id: UUID
) -> None:
    """Remove an archived project for good.

    Its files and research are kept: they move out of the project and stay
    in the user's library and research history.
    """
    project = _get_archived_project(session, project_id, user_id)
    actor = actor_for_user(session, user_id)
    project_id_str = str(project.id)
    session.execute(
        update(Document)
        .where(Document.project_id == project.id)
        .values(project_id=None)
    )
    session.execute(
        update(Research)
        .where(Research.project_id == project.id)
        .values(project_id=None)
    )
    session.delete(project)
    _commit(session)
    publish_realtime_event(
        [project_room(project_id_str)],
        "project.deleted",
        {"projectId": project_id_str},
        actor=actor,
    )
