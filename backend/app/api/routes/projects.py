from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.schemas.projects import (
    ResearchProjectCreate,
    ResearchProjectListResponse,
    ResearchProjectResponse,
    ResearchProjectUpdate,
)
from app.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=ResearchProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ResearchProjectCreate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchProjectResponse:
    return project_service.create_project(session, payload, user.id)


@router.get("", response_model=ResearchProjectListResponse)
def list_projects(
    session: DatabaseSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_archived: Annotated[
        bool,
        Query(alias="includeArchived"),
    ] = False,
) -> ResearchProjectListResponse:
    items, total = project_service.list_projects(
        session,
        user.id,
        search=search,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return ResearchProjectListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ResearchProjectResponse)
def get_project(
    project_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchProjectResponse:
    return project_service.get_project(session, project_id, user.id)


@router.patch("/{project_id}", response_model=ResearchProjectResponse)
def update_project(
    project_id: UUID,
    payload: ResearchProjectUpdate,
    session: DatabaseSession,
    user: CurrentUser,
) -> ResearchProjectResponse:
    return project_service.update_project(session, project_id, payload, user.id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(
    project_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    project_service.archive_project(session, project_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
