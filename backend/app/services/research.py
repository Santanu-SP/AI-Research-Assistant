from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.domain.research import (
    ResearchProgressStage,
    ResearchProgressStepStatus,
    ResearchStatus,
)
from app.domain.states import ProjectStatus
from app.models.research import Research
from app.schemas.research import (
    ResearchCreate,
    ResearchProgressResponse,
    ResearchProgressStep,
    ResearchUpdate,
)

FALLBACK_TITLE_MAX_LENGTH = 80
PROGRESS_STAGES: tuple[tuple[ResearchProgressStage, str], ...] = (
    (ResearchProgressStage.PLANNING, "Planning research"),
    (ResearchProgressStage.SEARCHING_SOURCES, "Searching sources"),
    (
        ResearchProgressStage.FINDING_DOCUMENTS,
        "Finding relevant uploaded documents",
    ),
    (ResearchProgressStage.REVIEWING_EVIDENCE, "Reviewing evidence"),
    (ResearchProgressStage.BUILDING_SYNTHESIS, "Building synthesis"),
)
PROJECT_STATUS_STAGE_MAP: dict[ProjectStatus, ResearchProgressStage] = {
    ProjectStatus.PAPERS_DISCOVERED: ResearchProgressStage.SEARCHING_SOURCES,
    ProjectStatus.PAPERS_SELECTED: ResearchProgressStage.FINDING_DOCUMENTS,
    ProjectStatus.PROCESSING: ResearchProgressStage.FINDING_DOCUMENTS,
    ProjectStatus.RESEARCH_READY: ResearchProgressStage.REVIEWING_EVIDENCE,
    ProjectStatus.ANALYZING: ResearchProgressStage.REVIEWING_EVIDENCE,
    ProjectStatus.REVIEW_READY: ResearchProgressStage.BUILDING_SYNTHESIS,
    ProjectStatus.REPORT_READY: ResearchProgressStage.BUILDING_SYNTHESIS,
}


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
        project_status=ProjectStatus.DRAFT,
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


def map_project_status(
    project_status: ProjectStatus,
    *,
    started: bool,
    current_stage: ResearchProgressStage | None,
) -> tuple[ResearchStatus, ResearchProgressStage | None]:
    """Map one internal workflow milestone to its stable public progress state."""
    if project_status == ProjectStatus.DRAFT:
        if started:
            return ResearchStatus.RESEARCHING, ResearchProgressStage.PLANNING
        return ResearchStatus.DRAFT, None
    if project_status == ProjectStatus.PROCESSING_FAILED:
        return ResearchStatus.FAILED, current_stage
    if project_status == ProjectStatus.REPORT_READY:
        return ResearchStatus.COMPLETED, ResearchProgressStage.BUILDING_SYNTHESIS
    return ResearchStatus.RESEARCHING, PROJECT_STATUS_STAGE_MAP[project_status]


def _build_progress_steps(research: Research) -> list[ResearchProgressStep]:
    current_index = (
        next(
            (
                index
                for index, (stage, _) in enumerate(PROGRESS_STAGES)
                if stage == research.progress_stage
            ),
            None,
        )
        if research.progress_stage is not None
        else None
    )
    completed = research.project_status == ProjectStatus.REPORT_READY
    failed = research.project_status == ProjectStatus.PROCESSING_FAILED
    active = research.status == ResearchStatus.RESEARCHING

    steps = []
    for index, (stage, title) in enumerate(PROGRESS_STAGES):
        if completed:
            step_status = ResearchProgressStepStatus.COMPLETED
        elif current_index is None:
            step_status = ResearchProgressStepStatus.PENDING
        elif index < current_index:
            step_status = ResearchProgressStepStatus.COMPLETED
        elif index == current_index and failed:
            step_status = ResearchProgressStepStatus.FAILED
        elif index == current_index and active:
            step_status = ResearchProgressStepStatus.ACTIVE
        else:
            step_status = ResearchProgressStepStatus.PENDING
        steps.append(ResearchProgressStep(id=stage, title=title, status=step_status))
    return steps


def get_research_progress(
    session: Session,
    research_id: UUID,
) -> ResearchProgressResponse:
    research = get_research(session, research_id)
    current_step_index = (
        next(
            index
            for index, (stage, _) in enumerate(PROGRESS_STAGES)
            if stage == research.progress_stage
        )
        if research.progress_stage is not None
        else None
    )
    return ResearchProgressResponse(
        id=research.id,
        question=research.question,
        status=research.status,
        research_depth=research.research_depth,
        current_stage=research.progress_stage,
        current_step_index=current_step_index,
        steps=_build_progress_steps(research),
        sources_discovered=research.sources_discovered,
        sources_reviewed=research.sources_reviewed,
        documents_found=research.documents_found,
        started_at=research.started_at,
        stage_started_at=research.stage_started_at,
        updated_at=research.updated_at,
        completed_at=research.completed_at,
        failed_at=research.failed_at,
    )


def start_research(session: Session, research_id: UUID) -> Research:
    """Start progress for trusted internal callers without executing research."""
    research = get_research(session, research_id)
    if research.started_at is not None or research.status != ResearchStatus.DRAFT:
        raise AppError(
            "Research has already started",
            status_code=409,
            code="research_already_started",
        )

    timestamp = utc_now()
    summary_status, progress_stage = map_project_status(
        ProjectStatus.DRAFT,
        started=True,
        current_stage=research.progress_stage,
    )
    research.status = summary_status
    research.project_status = ProjectStatus.DRAFT
    research.progress_stage = progress_stage
    research.sources_discovered = 0
    research.sources_reviewed = 0
    research.documents_found = 0
    research.started_at = timestamp
    research.stage_started_at = timestamp
    research.completed_at = None
    research.failed_at = None
    research.updated_at = timestamp
    _commit(session)
    session.refresh(research)
    return research


def update_research_lifecycle(
    session: Session,
    research_id: UUID,
    project_status: ProjectStatus,
) -> Research:
    """Apply a trusted internal workflow milestone to persisted progress."""
    research = get_research(session, research_id)
    if research.started_at is None:
        raise AppError(
            "Research progress has not started",
            status_code=409,
            code="research_not_started",
        )

    timestamp = utc_now()
    summary_status, progress_stage = map_project_status(
        project_status,
        started=True,
        current_stage=research.progress_stage,
    )
    if progress_stage != research.progress_stage:
        research.stage_started_at = timestamp

    research.status = summary_status
    research.project_status = project_status
    research.progress_stage = progress_stage
    research.completed_at = (
        timestamp if project_status == ProjectStatus.REPORT_READY else None
    )
    research.failed_at = (
        timestamp if project_status == ProjectStatus.PROCESSING_FAILED else None
    )
    research.updated_at = timestamp
    _commit(session)
    session.refresh(research)
    return research


def update_progress_counts(
    session: Session,
    research_id: UUID,
    *,
    sources_discovered: int | None = None,
    sources_reviewed: int | None = None,
    documents_found: int | None = None,
) -> Research:
    """Persist factual counters supplied by trusted internal callers."""
    research = get_research(session, research_id)
    if all(
        value is None
        for value in (sources_discovered, sources_reviewed, documents_found)
    ):
        raise AppError(
            "At least one progress count must be provided",
            status_code=422,
            code="invalid_research_progress_counts",
        )

    next_sources_discovered = (
        research.sources_discovered
        if sources_discovered is None
        else sources_discovered
    )
    next_sources_reviewed = (
        research.sources_reviewed if sources_reviewed is None else sources_reviewed
    )
    next_documents_found = (
        research.documents_found if documents_found is None else documents_found
    )
    if (
        next_sources_discovered < 0
        or next_sources_reviewed < 0
        or next_documents_found < 0
        or next_sources_reviewed > next_sources_discovered
    ):
        raise AppError(
            "Research progress counts are invalid",
            status_code=422,
            code="invalid_research_progress_counts",
        )

    research.sources_discovered = next_sources_discovered
    research.sources_reviewed = next_sources_reviewed
    research.documents_found = next_documents_found
    research.updated_at = utc_now()
    _commit(session)
    session.refresh(research)
    return research


def mark_research_completed(session: Session, research_id: UUID) -> Research:
    return update_research_lifecycle(session, research_id, ProjectStatus.REPORT_READY)


def mark_research_failed(session: Session, research_id: UUID) -> Research:
    return update_research_lifecycle(
        session,
        research_id,
        ProjectStatus.PROCESSING_FAILED,
    )


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
