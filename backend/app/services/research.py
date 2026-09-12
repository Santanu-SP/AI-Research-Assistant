from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.domain.research import ResearchStatus
from app.models.research import Research
from app.schemas.research import ResearchCreate, ResearchUpdate

FALLBACK_TITLE_MAX_LENGTH = 80


def build_fallback_title(question: str) -> str:
    normalized = " ".join(question.split())
    if len(normalized) <= FALLBACK_TITLE_MAX_LENGTH:
        return normalized

    shortened = normalized[: FALLBACK_TITLE_MAX_LENGTH - 3].rstrip(" ,.;:-")
    return f"{shortened}..."


def _commit(session: Session) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(
            "The research record could not be saved",
            status_code=500,
            code="research_persistence_error",
        ) from exc


def create_research(session: Session, payload: ResearchCreate) -> Research:
    research = Research(
        question=payload.question,
        title=payload.title or build_fallback_title(payload.question),
        domain=payload.domain,
        research_depth=payload.research_depth,
        status=ResearchStatus.DRAFT,
    )
    session.add(research)
    _commit(session)
    session.refresh(research)
    return research


def list_research(
    session: Session,
    *,
    search: str | None,
    domain: str | None,
    status: ResearchStatus | None,
    limit: int,
    offset: int,
    include_archived: bool,
) -> tuple[list[Research], int]:
    filters = []
    normalized_search = search.strip() if search else None
    normalized_domain = domain.strip() if domain else None

    if not include_archived:
        filters.append(Research.archived_at.is_(None))
    if normalized_search:
        filters.append(
            or_(
                Research.title.icontains(normalized_search, autoescape=True),
                Research.question.icontains(normalized_search, autoescape=True),
            )
        )
    if normalized_domain:
        filters.append(func.lower(Research.domain) == normalized_domain.lower())
    if status is not None:
        filters.append(Research.status == status)

    total = session.scalar(
        select(func.count()).select_from(Research).where(*filters)
    )
    statement = (
        select(Research)
        .where(*filters)
        .order_by(Research.updated_at.desc(), Research.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(session.scalars(statement).all())
    return items, total or 0


def get_research(session: Session, research_id: UUID) -> Research:
    research = session.scalar(
        select(Research).where(
            Research.id == research_id,
            Research.archived_at.is_(None),
        )
    )
    if research is None:
        raise AppError(
            "Research not found",
            status_code=404,
            code="research_not_found",
        )
    return research


def update_research(
    session: Session,
    research_id: UUID,
    payload: ResearchUpdate,
) -> Research:
    research = get_research(session, research_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(research, field, value)
    research.updated_at = utc_now()

    _commit(session)
    session.refresh(research)
    return research


def archive_research(session: Session, research_id: UUID) -> None:
    research = get_research(session, research_id)
    archived_at = utc_now()
    research.archived_at = archived_at
    research.updated_at = archived_at
    _commit(session)
