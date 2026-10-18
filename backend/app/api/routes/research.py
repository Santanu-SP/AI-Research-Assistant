"""API endpoints for hybrid retrieval, grounded RAG queries, and research run management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.domain.research import ResearchStatus
from app.schemas.rag import ResearchQueryRequest, ResearchQueryResponse
from app.schemas.reports import ComposedReportResponse
from app.schemas.research import (
    ResearchCreate,
    ResearchListResponse,
    ResearchProgressResponse,
    ResearchResponse,
    ResearchUpdate,
)
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services import rag as rag_service
from app.services import reports as reports_service
from app.services import research as research_service
from app.services import retrieval as retrieval_service

router = APIRouter(prefix="/research", tags=["research"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/retrieve", response_model=RetrievalResponse)
def retrieve_evidence(
    payload: RetrievalRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> RetrievalResponse:
    """Retrieve hybrid semantic + keyword candidate chunks for a query."""
    return RetrievalResponse(
        items=retrieval_service.retrieve(
            session,
            user.id,
            payload.query,
            request.app.state.settings,
            project_id=payload.project_id,
        )
    )


@router.post(
    "/query",
    response_model=ResearchQueryResponse,
    status_code=status.HTTP_201_CREATED,
)
def query_research(
    payload: ResearchQueryRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> ResearchQueryResponse:
    """Execute a full grounded RAG query and persist the generated report."""
    return rag_service.run_query(
        session,
        user.id,
        payload,
        request.app.state.settings,
    )


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    payload: ResearchCreate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    """Create a new draft research record."""
    return research_service.create_research(session, payload, user.id)


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
    """List research runs owned by the authenticated user."""
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
    """Retrieve progress stepper status and source counts for a research run."""
    return research_service.get_research_progress(session, research_id, user.id)


@router.get("/{research_id}/report", response_model=ComposedReportResponse)
def get_research_report(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ComposedReportResponse:
    """Retrieve the composed report and cited sources for a completed research run."""
    return reports_service.get_composed_report(session, research_id, user.id)


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    """Retrieve summary metadata for a single research run."""
    return research_service.get_research(session, research_id, user.id)


@router.patch("/{research_id}", response_model=ResearchResponse)
def update_research(
    research_id: UUID,
    payload: ResearchUpdate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchResponse:
    """Update a research run's title, question, domain, or depth."""
    return research_service.update_research(session, research_id, payload, user.id)


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_research(
    research_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    """Archive a research run."""
    research_service.archive_research(session, research_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)