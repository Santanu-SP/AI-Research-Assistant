from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.domain.documents import DocumentStatus, DocumentType
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.services import documents as document_service
from app.services.storage import LocalDocumentStorage, get_document_storage

router = APIRouter(
    prefix="/projects/{project_id}/documents",
    tags=["project documents"],
)
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[LocalDocumentStorage, Depends(get_document_storage)]


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_document(
    project_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    return await document_service.create_document(
        session,
        file,
        storage,
        request.app.state.settings,
        user.id,
        project_id,
    )


@router.get("", response_model=DocumentListResponse)
def list_project_documents(
    project_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=255)] = None,
    document_status: Annotated[
        DocumentStatus | None,
        Query(alias="status"),
    ] = None,
    document_type: Annotated[
        DocumentType | None,
        Query(alias="type"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    items, total = document_service.list_documents(
        session,
        search=search,
        status=document_status,
        file_type=document_type,
        limit=limit,
        offset=offset,
        user_id=user.id,
        project_id=project_id,
    )
    return DocumentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
