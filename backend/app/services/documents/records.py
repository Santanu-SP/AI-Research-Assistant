from collections.abc import Callable
from uuid import UUID

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.models.document import Document
from app.models.project import ResearchProject
from app.services.rag.embeddings import EmbeddingService
from app.services.ingestion.pipeline import DocumentIngestionAdapter, ingest_document
from app.services.documents.storage import LocalDocumentStorage, StoredUpload, ValidatedUpload
from app.services.jobs import queue as job_queue
from app.services.research import projects as project_service


def _commit(session: Session, error_message: str) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(
            error_message,
            status_code=500,
            code="document_persistence_error",
        ) from exc


def _find_duplicate(
    session: Session,
    user_id: UUID,
    checksum: str,
    project_id: UUID | None,
) -> Document | None:
    # A null project is its own scope. Matching only on checksum would treat
    # a legacy unscoped upload as a duplicate of a project upload.
    filters = [
        Document.user_id == user_id,
        Document.checksum == checksum,
    ]
    if project_id is None:
        filters.append(Document.project_id.is_(None))
    else:
        filters.append(Document.project_id == project_id)
    return session.scalar(select(Document).where(*filters))


async def create_document(
    session: Session,
    upload: UploadFile,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
    project_id: UUID | None = None,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    notify_worker: Callable[[], None] | None = None,
) -> Document:
    # Database calls are blocking, so they run on the thread pool; only the
    # streamed upload itself is awaited on the event loop.
    if project_id is not None:
        await run_in_threadpool(project_service.get_project, session, project_id, user_id)
    metadata = storage.validate(upload)
    stored = await storage.save(upload, metadata.extension)
    document = await run_in_threadpool(
        _register_upload, session, storage, metadata, stored, user_id, project_id
    )
    return await start_ingestion(
        session,
        document,
        storage,
        settings,
        adapter=adapter,
        embeddings=embeddings,
        notify_worker=notify_worker,
    )


def _register_upload(
    session: Session,
    storage: LocalDocumentStorage,
    metadata: ValidatedUpload,
    stored: StoredUpload,
    user_id: UUID,
    project_id: UUID | None,
) -> Document:
    duplicate = _find_duplicate(session, user_id, stored.checksum, project_id)
    if duplicate is not None and duplicate.status == DocumentStatus.FAILED:
        # A failed copy should never block trying again: replace it.
        _remove_document(session, duplicate, storage)
        duplicate = None
    if duplicate is not None:
        storage.delete(stored.stored_name)
        raise AppError(
            "This document has already been uploaded in this project",
            status_code=409,
            code="duplicate_document",
        )
    document = Document(
        user_id=user_id,
        project_id=project_id,
        name=metadata.original_name,
        stored_name=stored.stored_name,
        file_type=metadata.file_type,
        mime_type=metadata.mime_type,
        size=stored.size,
        source_type=SourceType.UPLOADED_FILE,
        content_level=ContentLevel.USER_DOCUMENT,
        checksum=stored.checksum,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)

    try:
        _commit(session, "The document metadata could not be saved")
        session.refresh(document)
    except AppError:
        try:
            storage.delete(stored.stored_name)
        except AppError as cleanup_error:
            raise AppError(
                "Document metadata failed and its stored file could not be cleaned up",
                status_code=500,
                code="document_cleanup_error",
            ) from cleanup_error
        raise
    return document


async def start_ingestion(
    session: Session,
    document: Document,
    storage: LocalDocumentStorage,
    settings: Settings,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    notify_worker: Callable[[], None] | None = None,
) -> Document:
    """Ingest now (inline mode) or hand the document to the background worker."""
    if settings.ingestion_mode == "inline":
        return await ingest_document(
            session,
            document,
            storage.path_for(document.stored_name),
            settings,
            adapter=adapter,
            embeddings=embeddings,
        )
    def _enqueue() -> Document:
        job_queue.enqueue(session, job_queue.INGEST_DOCUMENT, document.id)
        session.refresh(document)
        return document

    queued = await run_in_threadpool(_enqueue)
    if notify_worker is not None:
        notify_worker()
    return queued


async def retry_document(
    session: Session,
    document_id: UUID,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    notify_worker: Callable[[], None] | None = None,
) -> Document:
    """Re-run ingestion for a document whose previous attempt failed."""
    document = await run_in_threadpool(get_document, session, document_id, user_id)
    if document.status != DocumentStatus.FAILED:
        raise AppError(
            "Only documents that failed processing can be retried",
            status_code=409,
            code="document_not_retryable",
        )
    if not storage.path_for(document.stored_name).is_file():
        raise AppError(
            "The stored file for this document is missing; upload it again",
            status_code=409,
            code="document_file_missing",
        )
    document.status = DocumentStatus.UPLOADED
    document.processing_error = None
    await run_in_threadpool(_commit, session, "The document could not be queued for processing")
    return await start_ingestion(
        session,
        document,
        storage,
        settings,
        adapter=adapter,
        embeddings=embeddings,
        notify_worker=notify_worker,
    )


def _remove_document(session: Session, document: Document, storage: LocalDocumentStorage) -> None:
    storage.delete(document.stored_name)
    session.delete(document)
    _commit(session, "The previous failed copy could not be replaced")


def list_documents(
    session: Session,
    *,
    search: str | None,
    status: DocumentStatus | None,
    file_type: DocumentType | None,
    limit: int,
    offset: int,
    user_id: UUID,
    project_id: UUID | None = None,
) -> tuple[list[Document], int]:
    filters = [Document.user_id == user_id]
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)
        filters.append(Document.project_id == project_id)
    else:
        # Documents inside archived projects leave the global library too.
        filters.append(
            or_(
                Document.project_id.is_(None),
                Document.project_id.in_(
                    select(ResearchProject.id).where(
                        ResearchProject.user_id == user_id,
                        ResearchProject.archived_at.is_(None),
                    )
                ),
            )
        )
    normalized_search = search.strip() if search else None
    if normalized_search:
        filters.append(Document.name.icontains(normalized_search, autoescape=True))
    if status is not None:
        filters.append(Document.status == status)
    if file_type is not None:
        filters.append(Document.file_type == file_type)

    total = session.scalar(
        select(func.count()).select_from(Document).where(*filters)
    )
    statement = (
        select(Document)
        .where(*filters)
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    )
    documents = list(session.scalars(statement).all())
    return documents, total or 0


def get_document(session: Session, document_id: UUID, user_id: UUID) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    if document is None:
        raise AppError(
            "Document not found",
            status_code=404,
            code="document_not_found",
        )
    return document


def delete_document(
    session: Session,
    document_id: UUID,
    storage: LocalDocumentStorage,
    user_id: UUID,
) -> None:
    document = get_document(session, document_id, user_id)
    storage.delete(document.stored_name)
    session.delete(document)
    _commit(session, "The document metadata could not be deleted")


def mark_interrupted(session: Session, document_id: UUID, message: str) -> None:
    """Flag a document whose processing never finished so the user can retry."""
    document = session.get(Document, document_id)
    if document is None or document.status == DocumentStatus.INDEXED:
        return
    document.status = DocumentStatus.FAILED
    document.processing_error = message[:1000]
    _commit(session, "The interrupted document could not be updated")
