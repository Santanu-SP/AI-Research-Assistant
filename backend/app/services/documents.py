from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.models.document import Document
from app.services.embeddings import EmbeddingService
from app.services.ingestion import DocumentIngestionAdapter, ingest_document
from app.services.storage import LocalDocumentStorage
from app.services import projects as project_service
from app.services.doi import normalize_doi

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
    project_id: UUID | None = None,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
) -> Document:
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)
    metadata = storage.validate(upload)
    stored = await storage.save(upload, metadata.extension)
    duplicate_filters = [
        Document.user_id == user_id,
        Document.checksum == stored.checksum,
    ]
    if project_id is None:
        duplicate_filters.append(Document.project_id.is_(None))
    else:
        duplicate_filters.append(Document.project_id == project_id)
    duplicate = session.scalar(select(Document).where(*duplicate_filters))
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

    return await ingest_document(
        session,
        document,
        storage.path_for(document.stored_name),
        settings,
        adapter=adapter,
        embeddings=embeddings,
    )


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
    source_types: list[SourceType] | None = None,
    content_levels: list[ContentLevel] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    doi: str | None = None,
) -> tuple[list[Document], int]:
    filters = [Document.user_id == user_id]
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)
        filters.append(Document.project_id == project_id)
    normalized_search = search.strip() if search else None
    if normalized_search:
        filters.append(
            or_(
                Document.name.icontains(normalized_search, autoescape=True),
                Document.title.icontains(normalized_search, autoescape=True),
                Document.doi.icontains(normalized_search, autoescape=True),
            )
        )
    if status is not None:
        filters.append(Document.status == status)
    if file_type is not None:
        filters.append(Document.file_type == file_type)
    if source_types:
        filters.append(Document.source_type.in_(source_types))
    if content_levels:
        filters.append(Document.content_level.in_(content_levels))
    if year_from is not None:
        filters.append(Document.publication_year >= year_from)
    if year_to is not None:
        filters.append(Document.publication_year <= year_to)
    if doi:
        filters.append(func.lower(Document.doi) == normalize_doi(doi))

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
