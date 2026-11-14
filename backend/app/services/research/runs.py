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
from app.domain.documents import DocumentStatus
from app.models.document import Document
from app.models.job import BackgroundJob
from app.models.report import Source
from app.models.research import Research
from app.schemas.research import (
    ResearchCreate,
    ResearchProgressResponse,
    ResearchProgressStep,
    ResearchUpdate,
)
from app.services.research import projects as project_service

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


def create_research(session: Session, payload: ResearchCreate, user_id: UUID | None = None) -> Research:
    if payload.project_id is not None:
        if user_id is None:
            raise AppError(
                "A project-scoped research run requires an authenticated user",
                status_code=422,
                code="research_project_user_required",
            )
        project_service.get_project(session, payload.project_id, user_id)
    research = Research(
        user_id=user_id,
        project_id=payload.project_id,
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
    user_id: UUID | None = None,
    project_id: UUID | None = None,
) -> tuple[list[Research], int]:
    filters = []
    if user_id is not None:
        filters.append(Research.user_id == user_id)
    if project_id is not None:
        if user_id is None:
            raise AppError(
                "A project-scoped research list requires an authenticated user",
                status_code=422,
                code="research_project_user_required",
            )
        project_service.get_project(session, project_id, user_id)
        filters.append(Research.project_id == project_id)
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


def get_research(session: Session, research_id: UUID, user_id: UUID | None = None) -> Research:
    filters = [Research.id == research_id, Research.archived_at.is_(None)]
    if user_id is not None:
        filters.append(Research.user_id == user_id)
    research = session.scalar(
        select(Research).where(*filters)
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


def _stage_index(stage: ResearchProgressStage | None) -> int | None:
    if stage is None:
        return None
    for index, (candidate, _title) in enumerate(PROGRESS_STAGES):
        if candidate == stage:
            return index
    return None


def _step_status(
    index: int,
    current_index: int | None,
    *,
    completed: bool,
    failed: bool,
    active: bool,
) -> ResearchProgressStepStatus:
    if completed:
        return ResearchProgressStepStatus.COMPLETED
    if current_index is None or index > current_index:
        return ResearchProgressStepStatus.PENDING
    if index < current_index:
        return ResearchProgressStepStatus.COMPLETED
    if failed:
        return ResearchProgressStepStatus.FAILED
    if active:
        return ResearchProgressStepStatus.ACTIVE
    return ResearchProgressStepStatus.PENDING


def _build_progress_steps(research: Research) -> list[ResearchProgressStep]:
    current_index = _stage_index(research.progress_stage)
    completed = research.project_status == ProjectStatus.REPORT_READY
    failed = research.project_status == ProjectStatus.PROCESSING_FAILED
    active = research.status == ResearchStatus.RESEARCHING

    steps = []
    for index, (stage, title) in enumerate(PROGRESS_STAGES):
        steps.append(
            ResearchProgressStep(
                id=stage,
                title=title,
                status=_step_status(
                    index,
                    current_index,
                    completed=completed,
                    failed=failed,
                    active=active,
                ),
            )
        )
    return steps


def get_research_progress(
    session: Session,
    research_id: UUID,
    user_id: UUID | None = None,
) -> ResearchProgressResponse:
    research = get_research(session, research_id, user_id)
    current_step_index = _stage_index(research.progress_stage)
    documents_ready, documents_preparing = _document_readiness(session, research)
    failure_reason = (
        _failure_reason(session, research, documents_ready)
        if research.status == ResearchStatus.FAILED
        else None
    )
    return ResearchProgressResponse(
        id=research.id,
        project_id=research.project_id,
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
        failure_reason=failure_reason,
        documents_ready=documents_ready,
        documents_preparing=documents_preparing,
    )


def _document_readiness(session: Session, research: Research) -> tuple[int, int]:
    """Count ready and still-processing documents in the run's scope."""
    if research.user_id is None:
        return 0, 0
    filters = [Document.user_id == research.user_id]
    if research.project_id is not None:
        filters.append(Document.project_id == research.project_id)
    counts = dict(
        session.execute(
            select(Document.status, func.count(Document.id))
            .where(*filters)
            .group_by(Document.status)
        ).all()
    )
    ready = int(counts.get(DocumentStatus.INDEXED, 0))
    preparing = int(counts.get(DocumentStatus.UPLOADED, 0)) + int(
        counts.get(DocumentStatus.PROCESSING, 0)
    )
    return ready, preparing


# Error codes from the pipeline mapped to the few reasons the UI explains.
_FAILURE_REASONS = {
    "generation_unavailable": "model_unavailable",
    "generation_invalid_request": "model_unavailable",
    "daily_model_quota_exceeded": "quota_reached",
}


def _failure_reason(session: Session, research: Research, documents_ready: int) -> str:
    last_error = session.scalar(
        select(BackgroundJob.last_error)
        .where(BackgroundJob.target_id == research.id, BackgroundJob.last_error.is_not(None))
        .order_by(BackgroundJob.updated_at.desc())
        .limit(1)
    )
    if last_error:
        code = last_error.split(":", 1)[0].strip()
        if code in _FAILURE_REASONS:
            return _FAILURE_REASONS[code]
    if documents_ready == 0:
        return "no_ready_documents"
    return "unexpected"


def restart_research(session: Session, research_id: UUID, *, commit: bool = True) -> Research:
    """Put a failed run back to the start so it can be run again in place."""
    research = get_research(session, research_id)
    if research.status != ResearchStatus.FAILED:
        raise AppError(
            "Only research that stopped before finishing can be run again",
            status_code=409,
            code="research_not_retryable",
        )
    timestamp = utc_now()
    research.status = ResearchStatus.RESEARCHING
    research.project_status = ProjectStatus.DRAFT
    research.progress_stage = ResearchProgressStage.PLANNING
    research.sources_discovered = 0
    research.sources_reviewed = 0
    research.documents_found = 0
    research.started_at = timestamp
    research.stage_started_at = timestamp
    research.completed_at = None
    research.failed_at = None
    research.updated_at = timestamp
    if commit:
        _commit(session)
        session.refresh(research)
    else:
        session.flush()
    return research


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


def advance_research_progress(
    session: Session,
    research_id: UUID,
    *,
    project_status: ProjectStatus | None = None,
    sources_discovered: int | None = None,
    sources_reviewed: int | None = None,
    documents_found: int | None = None,
    commit: bool = True,
) -> Research:
    """Atomically apply progress counters and/or lifecycle stage in a single transaction."""
    research = get_research(session, research_id)
    timestamp = utc_now()

    if any(value is not None for value in (sources_discovered, sources_reviewed, documents_found)):
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

    if project_status is not None:
        if research.started_at is None:
            raise AppError(
                "Research progress has not started",
                status_code=409,
                code="research_not_started",
            )
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
    if commit:
        _commit(session)
        session.refresh(research)
    else:
        session.flush()
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
    user_id: UUID | None = None,
) -> Research:
    research = get_research(session, research_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(research, field, value)
    research.updated_at = utc_now()

    _commit(session)
    session.refresh(research)
    return research


def archive_research(session: Session, research_id: UUID, user_id: UUID | None = None) -> None:
    research = get_research(session, research_id, user_id)
    archived_at = utc_now()
    research.archived_at = archived_at
    research.updated_at = archived_at
    _commit(session)


def attach_source_counts(session: Session, records: list[Research]) -> list[Research]:
    """Fill the response-only ``source_count`` with one grouped query."""
    if not records:
        return records
    counts = dict(
        session.execute(
            select(Source.research_id, func.count(Source.id))
            .where(Source.research_id.in_([record.id for record in records]))
            .group_by(Source.research_id)
        ).all()
    )
    for record in records:
        record.source_count = int(counts.get(record.id, 0))  # type: ignore[attr-defined]
    return records
