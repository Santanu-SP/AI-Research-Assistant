import logging
from uuid import UUID

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus, DocumentType
from app.models.document import Document, DocumentChunk
from app.services.pdf_extraction import PdfExtractionError, extract_pdf
from app.services.embeddings import embedding_service_for
from app.services.storage import LocalDocumentStorage
from app.services.text_processing import chunk_pages


logger = logging.getLogger(__name__)


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


async def create_document(
    session: Session,
    upload: UploadFile,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
) -> Document:
    metadata = storage.validate(upload)
    stored = await storage.save(upload, metadata.extension)
    document = Document(
        user_id=user_id,
        name=metadata.original_name,
        stored_name=stored.stored_name,
        file_type=metadata.file_type,
        mime_type=metadata.mime_type,
        size=stored.size,
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

    document.status = DocumentStatus.PROCESSING
    _commit(session, "The document processing status could not be saved")

    try:
        extracted = await run_in_threadpool(
            extract_pdf, storage.path_for(document.stored_name)
        )
        prepared_chunks = chunk_pages(
            document.id,
            extracted.pages,
            chunk_size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )
        if not prepared_chunks:
            raise PdfExtractionError("The PDF contains no extractable text")

        document.title = extracted.title
        document.authors = extracted.authors
        document.doi = extracted.doi
        document.page_count = extracted.page_count
        document.processing_error = None
        document.chunks = [
            DocumentChunk(
                id=chunk.id,
                document_id=chunk.document_id,
                text=chunk.text,
                page=chunk.page,
                section=chunk.section,
                chunk_index=chunk.chunk_index,
            )
            for chunk in prepared_chunks
        ]
        if settings.embedding_enabled:
            if session.bind is None or session.bind.dialect.name != "postgresql":
                raise AppError("Document indexing requires PostgreSQL with pgvector", status_code=503, code="embedding_backend_unavailable")
            vectors = embedding_service_for(settings).embed_documents([chunk.text for chunk in prepared_chunks])
            if len(vectors) != len(document.chunks):
                raise AppError("Embedding generation returned an invalid batch", status_code=500, code="embedding_batch_mismatch")
            for chunk, vector in zip(document.chunks, vectors, strict=True):
                chunk.embedding = vector
        document.status = DocumentStatus.INDEXED
        _commit(session, "The processed document could not be saved")
        session.refresh(document)
        logger.info(
            "Indexed document %s with %d pages and %d chunks",
            document.id,
            extracted.page_count,
            len(prepared_chunks),
        )
        return document
    except (PdfExtractionError, AppError) as exc:
        session.rollback()
        failed_document = session.get(Document, document.id)
        if failed_document is None:
            raise AppError(
                "The document processing failure could not be recorded",
                status_code=500,
                code="document_persistence_error",
            ) from exc
        failed_document.status = DocumentStatus.FAILED
        failed_document.processing_error = str(exc)
        _commit(session, "The document processing failure could not be saved")
        logger.warning("Document %s failed processing: %s", document.id, exc)
        raise AppError(
            "The document could not be indexed",
            status_code=422 if isinstance(exc, PdfExtractionError) else exc.status_code,
            code="pdf_processing_failed" if isinstance(exc, PdfExtractionError) else exc.code,
        ) from exc


def list_documents(
    session: Session,
    *,
    search: str | None,
    status: DocumentStatus | None,
    file_type: DocumentType | None,
    limit: int,
    offset: int,
    user_id: UUID,
) -> tuple[list[Document], int]:
    filters = [Document.user_id == user_id]
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
    document = session.scalar(select(Document).where(Document.id == document_id, Document.user_id == user_id))
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
