from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.uploads import enforce_upload_rate_limit, upload_status_code
from app.core.errors import AppError
from app.db.session import get_db
from app.domain.documents import DocumentStatus, DocumentType
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.services.documents import records as document_service
from app.services.documents.storage import LocalDocumentStorage, get_document_storage

router = APIRouter(prefix="/documents", tags=["documents"])
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[LocalDocumentStorage, Depends(get_document_storage)]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    response: Response,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    """Store a document and index it.

    Returns ``201`` with the indexed document in inline mode, or ``202`` with
    an ``uploaded`` document that the background worker will process.
    """
    enforce_upload_rate_limit(request, user.id)
    document = await document_service.create_document(
        session,
        file,
        storage,
        request.app.state.settings,
        user.id,
        notify_worker=request.app.state.job_worker.wake,
    )
    response.status_code = upload_status_code(document)
    return document


@router.get("", response_model=DocumentListResponse)
def list_documents(
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
    user: CurrentUser,
) -> DocumentResponse:
    return document_service.get_document(session, document_id, user.id)


@router.get("/{document_id}/file")
def open_document(
    document_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
    user: CurrentUser,
) -> FileResponse:
    document = document_service.get_document(session, document_id, user.id)
    path = storage.path_for(document.stored_name)
    if not path.is_file():
        raise AppError("Document file not found", status_code=404, code="document_file_not_found")
    # PDFs open in the browser viewer; Office files are always downloaded.
    disposition = "inline" if document.file_type == DocumentType.PDF else "attachment"
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.name,
        content_disposition_type=disposition,
        headers={
            "Cache-Control": "private, no-store",
            # The API's default-src 'none' policy would stop the browser's
            # built-in PDF viewer, so file responses only forbid framing.
            "Content-Security-Policy": "frame-ancestors 'none'",
        },
    )


@router.post("/{document_id}/retry", response_model=DocumentResponse)
async def retry_document(
    document_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> DocumentResponse:
    """Process a failed document again without uploading it a second time."""
    enforce_upload_rate_limit(request, user.id)
    document = await document_service.retry_document(
        session,
        document_id,
        storage,
        request.app.state.settings,
        user.id,
        notify_worker=request.app.state.job_worker.wake,
    )
    response.status_code = upload_status_code(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
    user: CurrentUser,
) -> Response:
    document_service.delete_document(session, document_id, storage, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
