"""Owned project source ingestion and listing endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.errors import AppError
from app.db.session import get_db
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.schemas.sources import DoiSourceCreate, OpenAlexSourceCreate, UrlSourceCreate
from app.services import documents as document_service
from app.services import sources as source_service
from app.services.storage import LocalDocumentStorage, get_document_storage


router = APIRouter(prefix="/projects/{project_id}/sources", tags=["project sources"])
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[LocalDocumentStorage, Depends(get_document_storage)]


@router.post("/url", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def add_url_source(
    project_id: UUID,
    payload: UrlSourceCreate,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    user: CurrentUser,
) -> DocumentResponse:
    return await source_service.create_url_source(
        session,
        user_id=user.id,
        project_id=project_id,
        url=payload.url,
        storage=storage,
        settings=request.app.state.settings,
    )


@router.post("/doi", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def add_doi_source(
    project_id: UUID,
    payload: DoiSourceCreate,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> DocumentResponse:
    return await source_service.create_doi_source(
        session,
        user_id=user.id,
        project_id=project_id,
        doi=payload.doi,
        settings=request.app.state.settings,
    )


@router.post(
    "/openalex", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def add_openalex_source(
    project_id: UUID,
    payload: OpenAlexSourceCreate,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> DocumentResponse:
    return await source_service.create_provider_source(
        session,
        user_id=user.id,
        project_id=project_id,
        source_type=SourceType.OPENALEX,
        identifier=payload.identifier,
        settings=request.app.state.settings,
    )


@router.post(
    "/crossref", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def add_crossref_source(
    project_id: UUID,
    payload: DoiSourceCreate,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> DocumentResponse:
    return await source_service.create_provider_source(
        session,
        user_id=user.id,
        project_id=project_id,
        source_type=SourceType.CROSSREF,
        identifier=payload.doi,
        settings=request.app.state.settings,
    )


@router.get("", response_model=DocumentListResponse)
def list_project_sources(
    project_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=255)] = None,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    document_type: Annotated[DocumentType | None, Query(alias="type")] = None,
    source_types: Annotated[list[SourceType] | None, Query(alias="sourceType")] = None,
    content_levels: Annotated[
        list[ContentLevel] | None, Query(alias="contentLevel")
    ] = None,
    year_from: Annotated[int | None, Query(alias="yearFrom", ge=1000, le=3000)] = None,
    year_to: Annotated[int | None, Query(alias="yearTo", ge=1000, le=3000)] = None,
    doi: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise AppError("yearFrom cannot be later than yearTo", status_code=422)
    items, total = document_service.list_documents(
        session,
        search=search,
        status=document_status,
        file_type=document_type,
        limit=limit,
        offset=offset,
        user_id=user.id,
        project_id=project_id,
        source_types=source_types,
        content_levels=content_levels,
        year_from=year_from,
        year_to=year_to,
        doi=doi,
    )
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)
