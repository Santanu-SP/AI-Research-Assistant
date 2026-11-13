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
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    SignedUrlResponse,
    UrlDocumentCreateRequest,
)
from app.services.documents import records as document_service
from app.services.documents.storage import DocumentStorageBackend, get_document_storage
from app.services.ingestion.pipeline import reembed_document

router = APIRouter(prefix="/documents", tags=["documents"])
DatabaseSession = Annotated[Session, Depends(get_db)]
DocumentStorage = Annotated[DocumentStorageBackend, Depends(get_document_storage)]


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


@router.post("/url", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_url_document(
    payload: UrlDocumentCreateRequest,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> DocumentResponse:
    """Ingest a YouTube video transcript or public web page into the unified document pipeline."""
    enforce_upload_rate_limit(request, user.id)
    document = await document_service.create_url_document(
        session,
        payload.url,
        storage,
        request.app.state.settings,
        user.id,
        payload.project_id,
        title=payload.title,
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


@router.get("/{document_id}/signed-url", response_model=SignedUrlResponse)
def get_document_signed_url(
    document_id: UUID,
    session: DatabaseSession,
    storage: DocumentStorage,
    request: Request,
    user: CurrentUser,
    expires_in: Annotated[int | None, Query(ge=60, le=86400)] = None,
) -> SignedUrlResponse:
    """Return a presigned R2 URL or authenticated file URL for downloading the document."""
    document = document_service.get_document(session, document_id, user.id)
    ttl = expires_in or request.app.state.settings.r2_signed_url_ttl_seconds
    presigned = storage.generate_presigned_url(
        document.stored_name,
        expires_in=ttl,
        filename=document.name,
    )
    if presigned:
        return SignedUrlResponse(
            document_id=document.id,
            url=presigned,
            expires_in_seconds=ttl,
            storage_backend="r2",
        )
    return SignedUrlResponse(
        document_id=document.id,
        url=f"/api/v1/documents/{document.id}/file",
        expires_in_seconds=ttl,
        storage_backend=document.storage_backend or "local",
    )


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


@router.post("/{document_id}/reembed", response_model=DocumentResponse)
def reembed_existing_document(
    document_id: UUID,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
    force: Annotated[bool, Query()] = False,
) -> DocumentResponse:
    """Recompute chunk embeddings only if the embedding model/version changed or force=true."""
    document = document_service.get_document(session, document_id, user.id)
    return reembed_document(
        session,
        document,
        request.app.state.settings,
        force=force,
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
