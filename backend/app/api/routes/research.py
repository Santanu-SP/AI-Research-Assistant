from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core import rate_limit
from app.db.session import get_db
from app.domain.research import ResearchStatus
from app.schemas.research import (
    ResearchCreate,
    ResearchListResponse,
    ResearchProgressResponse,
    ResearchResponse,
    ResearchUpdate,
)
from app.schemas.rag import ResearchQueryRequest, ResearchQueryResponse, ResearchRetryRequest
from app.schemas.reports import ComposedReportResponse
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.research import runs as research_service
from app.services.research import reports as reports_service
from app.services.rag import retrieval as retrieval_service
from app.services.rag import query as rag_service

router = APIRouter(prefix="/research", tags=["research"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/retrieve", response_model=RetrievalResponse)
def retrieve_evidence(
    payload: RetrievalRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> RetrievalResponse:
    _enforce_query_rate_limit(request, user.id)
    return RetrievalResponse(
        items=retrieval_service.retrieve(
            session,
            user.id,
            payload.query,
            request.app.state.settings,
            project_id=payload.project_id,
        )
    )


def _enforce_query_rate_limit(request: Request, user_id: UUID) -> None:
    rate_limit.enforce(
        request,
        "query",
        key=str(user_id),
        limit=request.app.state.settings.rate_limit_query_per_minute,
        window_seconds=60,
    )


@router.post("/query", response_model=ResearchQueryResponse, status_code=status.HTTP_201_CREATED)
def query_research(
    payload: ResearchQueryRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> ResearchQueryResponse:
    """Answer a question within this request (kept for inline project chat)."""
    _enforce_query_rate_limit(request, user.id)
    return rag_service.run_query(
        session,
        user.id,
        payload,
        request.app.state.settings,
    )


@router.post("/jobs", response_model=ResearchResponse, status_code=status.HTTP_202_ACCEPTED)
def queue_research_query(
    payload: ResearchQueryRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> ResearchResponse:
    """Start a research run in the background and return immediately.

    Poll ``GET /research/{id}/status`` for progress and fetch
    ``GET /research/{id}/report`` once it has completed.
    """
    _enforce_query_rate_limit(request, user.id)
    record = rag_service.queue_query(
        session,
        user.id,
        payload,
        request.app.state.settings,
    )
    request.app.state.job_worker.wake()
    return research_service.attach_source_counts(session, [record])[0]


@router.post(
    "/{research_id}/retry",
    response_model=ResearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_research(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
    payload: ResearchRetryRequest | None = None,
) -> ResearchResponse:
    """Run a failed research item again on the same record.

    The history keeps a single entry for the question. Send ``query`` to
    run an edited question in its place.
    """
    _enforce_query_rate_limit(request, user.id)
    record = rag_service.retry_research(
        session,
        user.id,
        research_id,
        payload or ResearchRetryRequest(),
        request.app.state.settings,
    )
    request.app.state.job_worker.wake()
    return research_service.attach_source_counts(session, [record])[0]


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    payload: ResearchCreate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    record = research_service.create_research(session, payload, user.id)
    return research_service.attach_source_counts(session, [record])[0]


@router.get("", response_model=ResearchListResponse)
def list_research(
    session: DatabaseSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=200)] = None,
    domain: Annotated[str | None, Query(max_length=120)] = None,
    research_status: Annotated[
        ResearchStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_archived: Annotated[
        bool,
        Query(alias="includeArchived"),
    ] = False,
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
) -> ResearchListResponse:
    items, total = research_service.list_research(
        session,
        search=search,
        domain=domain,
        status=research_status,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        user_id=user.id,
        project_id=project_id,
    )
    research_service.attach_source_counts(session, items)
    return ResearchListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{research_id}/status", response_model=ResearchProgressResponse)
def get_research_progress(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchProgressResponse:
    return research_service.get_research_progress(session, research_id, user.id)


@router.get("/{research_id}/report", response_model=ComposedReportResponse)
def get_research_report(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ComposedReportResponse:
    return reports_service.get_composed_report(session, research_id, user.id)


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    record = research_service.get_research(session, research_id, user.id)
    return research_service.attach_source_counts(session, [record])[0]


@router.patch("/{research_id}", response_model=ResearchResponse)
def update_research(
    research_id: UUID,
    payload: ResearchUpdate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    record = research_service.update_research(session, research_id, payload, user.id)
    return research_service.attach_source_counts(session, [record])[0]


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_research(research_id: UUID, session: DatabaseSession, user: CurrentUser) -> Response:
    research_service.archive_research(session, research_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
