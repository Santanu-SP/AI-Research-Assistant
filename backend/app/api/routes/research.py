from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.research import ResearchStatus
from app.schemas.research import (
    ResearchCreate,
    ResearchListResponse,
    ResearchProgressResponse,
    ResearchResponse,
    ResearchUpdate,
)
from app.services import research as research_service

router = APIRouter(prefix="/research", tags=["research"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    payload: ResearchCreate,
    session: DatabaseSession,
) -> ResearchResponse:
    return research_service.create_research(session, payload)


@router.get("", response_model=ResearchListResponse)
def list_research(
    session: DatabaseSession,
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
) -> ResearchListResponse:
    items, total = research_service.list_research(
        session,
        search=search,
        domain=domain,
        status=research_status,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
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
) -> ResearchProgressResponse:
    return research_service.get_research_progress(session, research_id)


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: UUID,
    session: DatabaseSession,
) -> ResearchResponse:
    return research_service.get_research(session, research_id)


@router.patch("/{research_id}", response_model=ResearchResponse)
def update_research(
    research_id: UUID,
    payload: ResearchUpdate,
    session: DatabaseSession,
) -> ResearchResponse:
    return research_service.update_research(session, research_id, payload)


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_research(research_id: UUID, session: DatabaseSession) -> Response:
    research_service.archive_research(session, research_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
