from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.uploads import enforce_upload_rate_limit
from app.core import rate_limit
from app.db.session import get_db
from app.schemas.discovery import (
    DiscoveryImportRequest,
    DiscoveryImportResponse,
    DiscoverySearchRequest,
    DiscoverySearchResponse,
    DiscoveryStatusResponse,
)
from app.services.discovery import service as discovery_service
from app.services.documents.storage import DocumentStorageBackend, get_document_storage

router = APIRouter(prefix="/discovery", tags=["discovery"])
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[DocumentStorageBackend, Depends(get_document_storage)]


@router.get("/status", response_model=DiscoveryStatusResponse)
def discovery_status(request: Request, user: CurrentUser) -> DiscoveryStatusResponse:
    del user
    settings = request.app.state.settings
    return DiscoveryStatusResponse(
        enabled=bool(settings.discovery_enabled),
        scopes=["all", "scholarly", "web"],
        providers=["openalex", "crossref", "arxiv", "wikipedia", "news"],
        auto_import_limit=settings.discovery_auto_import_limit,
    )


@router.post("/search", response_model=DiscoverySearchResponse)
def search_external_sources(
    payload: DiscoverySearchRequest,
    session: DatabaseSession,
    user: CurrentUser,
    request: Request,
) -> DiscoverySearchResponse:
    rate_limit.enforce(
        request,
        "discovery-search",
        key=str(user.id),
        limit=30,
        window_seconds=60,
    )
    return discovery_service.search_and_annotate(
        session,
        user_id=user.id,
        query=payload.query,
        scope=payload.scope,
        limit=payload.limit,
        project_id=payload.project_id,
        settings=request.app.state.settings,
    )


@router.post(
    "/import",
    response_model=DiscoveryImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_external_sources(
    payload: DiscoveryImportRequest,
    session: DatabaseSession,
    storage: DocumentStorage,
    user: CurrentUser,
    request: Request,
) -> DiscoveryImportResponse:
    enforce_upload_rate_limit(request, user.id)
    return discovery_service.import_discovered_sources(
        session,
        payload.items,
        storage=storage,
        settings=request.app.state.settings,
        user_id=user.id,
        project_id=payload.project_id,
        fetch_full_text=payload.fetch_full_text,
    )
