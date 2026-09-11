from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.documents import DocumentStatus, DocumentType
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.services import documents as document_service
from app.services.storage import LocalDocumentStorage, get_document_storage

router = APIRouter(prefix="/documents", tags=["documents"])
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[LocalDocumentStorage, Depends(get_document_storage)]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DatabaseSession,
    storage: DocumentStorage,
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    return await document_service.create_document(session, file, storage)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    session: DatabaseSession,
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
    )
    return DocumentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    session: DatabaseSession,
) -> DocumentResponse:
    return document_service.get_document(session, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
) -> Response:
    document_service.delete_document(session, document_id, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
