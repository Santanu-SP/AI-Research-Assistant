from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.models.project import ResearchProject
from app.schemas.projects import ResearchProjectCreate, ResearchProjectUpdate


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
    filters = [ResearchProject.user_id == user_id]
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
    return items, total or 0


def get_project(
    session: Session,
    project_id: UUID,
    user_id: UUID,
    *,
    include_archived: bool = False,
) -> ResearchProject:
    filters = [
        ResearchProject.id == project_id,
        ResearchProject.user_id == user_id,
    ]
    if not include_archived:
        filters.append(ResearchProject.archived_at.is_(None))
    project = session.scalar(select(ResearchProject).where(*filters))
    if project is None:
        raise AppError(
            "Research project not found",
            status_code=404,
            code="research_project_not_found",
        )
    return project


def update_project(
    session: Session,
    project_id: UUID,
    payload: ResearchProjectUpdate,
    user_id: UUID,
) -> ResearchProject:
    project = get_project(session, project_id, user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = utc_now()
    _commit(session)
    session.refresh(project)
    return project


def archive_project(session: Session, project_id: UUID, user_id: UUID) -> None:
    project = get_project(session, project_id, user_id)
    timestamp = utc_now()
    project.archived_at = timestamp
    project.updated_at = timestamp
    _commit(session)
