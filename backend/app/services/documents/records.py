from collections.abc import Callable
import hashlib
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.realtime_bus import project_room, publish_realtime_event
from app.domain.collaboration import CollaboratorRole
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.models.collaboration import ResearchMember
from app.models.document import Document
from app.models.project import ResearchProject
from app.models.research import Research, research_documents
from app.services.collaboration.access import (
    accessible_project_ids_select,
    actor_for_user,
    require_document_access,
    require_project_access,
)
from app.services.rag.embeddings import EmbeddingService
from app.services.ingestion.pipeline import DocumentIngestionAdapter, ingest_document
from app.services.documents.storage import LocalDocumentStorage, StoredUpload, ValidatedUpload
from app.services.jobs import queue as job_queue


def _broadcast_document_event(
    session: Session,
    document: Document,
    event_type: str,
    *,
    actor_id: UUID | None = None,
) -> None:
    if document.project_id is None:
        return
    publish_realtime_event(
        [project_room(document.project_id)],
        event_type,
        {
            "projectId": str(document.project_id),
            "documentId": str(document.id),
            "name": document.name,
            "status": str(document.status.value),
            "processingStage": document.processing_stage,
            "processingProgress": document.processing_progress,
        },
        actor=actor_for_user(session, actor_id),
    )


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
    # Project uploads deduplicate across the whole project so teammates don't
    # re-upload identical files; personal library uploads deduplicate per user.
    if project_id is not None:
        filters = [
            Document.project_id == project_id,
            Document.checksum == checksum,
        ]
    else:
        filters = [
            Document.user_id == user_id,
            Document.project_id.is_(None),
            Document.checksum == checksum,
        ]
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
        await run_in_threadpool(
            require_project_access,
            session,
            project_id,
            user_id,
            min_role=CollaboratorRole.EDITOR,
        )
    metadata = storage.validate(upload)
    stored = await storage.save(upload, metadata.extension)
    document = await run_in_threadpool(
        _register_upload, session, storage, metadata, stored, user_id, project_id
    )
    await run_in_threadpool(
        _broadcast_document_event, session, document, "document.added", actor_id=user_id
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
            # The caller owns this copy; the New research page attaches it.
            details={"documentId": str(duplicate.id)},
        )
    document = Document(
        user_id=user_id,
        project_id=project_id,
        name=metadata.original_name,
        stored_name=stored.stored_name,
        storage_backend=stored.storage_backend,
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


def _is_youtube_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }


def _register_url_document(
    session: Session,
    storage: LocalDocumentStorage,
    url: str,
    title: str | None,
    user_id: UUID,
    project_id: UUID | None,
) -> Document:
    from app.services.ingestion.web import validate_public_url

    normalized_url = url.strip()
    validate_public_url(normalized_url)
    is_yt = _is_youtube_url(normalized_url)
    checksum = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    duplicate = _find_duplicate(session, user_id, checksum, project_id)
    if duplicate is not None and duplicate.status == DocumentStatus.FAILED:
        _remove_document(session, duplicate, storage)
        duplicate = None
    if duplicate is not None:
        raise AppError(
            "This URL source has already been added to this project",
            status_code=409,
            code="duplicate_document",
            details={"documentId": str(duplicate.id)},
        )

    extension = ".youtube" if is_yt else ".web"
    stored_name = f"{uuid4().hex}{extension}"
    storage.root.mkdir(parents=True, exist_ok=True)
    descriptor_path = storage._path_for(stored_name)
    descriptor_bytes = normalized_url.encode("utf-8")
    descriptor_path.write_bytes(descriptor_bytes)

    parsed_url = urlparse(normalized_url)
    display_name = (
        (title or "").strip()
        or (f"YouTube ({parsed_url.path.strip('/') or parsed_url.query})" if is_yt else f"{parsed_url.netloc}{parsed_url.path}")
    )[:255]
    document = Document(
        user_id=user_id,
        project_id=project_id,
        name=display_name or normalized_url[:255],
        stored_name=stored_name,
        storage_backend=storage.storage_backend_name,
        file_type=DocumentType.YOUTUBE if is_yt else DocumentType.WEB,
        mime_type="text/uri-list",
        size=len(descriptor_bytes),
        source_type=SourceType.YOUTUBE_VIDEO if is_yt else SourceType.WEB_PAGE,
        source_url=normalized_url,
        source_uri=normalized_url,
        content_level=ContentLevel.TRANSCRIPT if is_yt else ContentLevel.WEB_PAGE,
        checksum=checksum,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    try:
        _commit(session, "The URL source metadata could not be saved")
        session.refresh(document)
    except AppError:
        descriptor_path.unlink(missing_ok=True)
        raise
    return document


async def create_url_document(
    session: Session,
    url: str,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
    project_id: UUID | None = None,
    *,
    title: str | None = None,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    notify_worker: Callable[[], None] | None = None,
) -> Document:
    if project_id is not None:
        await run_in_threadpool(
            require_project_access,
            session,
            project_id,
            user_id,
            min_role=CollaboratorRole.EDITOR,
        )
    document = await run_in_threadpool(
        _register_url_document,
        session,
        storage,
        url,
        title,
        user_id,
        project_id,
    )
    await run_in_threadpool(
        _broadcast_document_event, session, document, "document.added", actor_id=user_id
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


def _job_kind_for_document(document: Document) -> str:
    if document.file_type == DocumentType.AUDIO:
        return job_queue.INGEST_AUDIO
    if document.file_type == DocumentType.VIDEO:
        return job_queue.INGEST_VIDEO
    if document.file_type in (DocumentType.YOUTUBE, DocumentType.WEB):
        return job_queue.INGEST_URL
    return job_queue.INGEST_DOCUMENT


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
        kind = _job_kind_for_document(document)
        job_queue.enqueue(session, kind, document.id, settings=settings)
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
    document = await run_in_threadpool(
        get_document, session, document_id, user_id, min_role=CollaboratorRole.EDITOR
    )
    if document.status != DocumentStatus.FAILED:
        raise AppError(
            "Only documents that failed processing can be retried",
            status_code=409,
            code="document_not_retryable",
        )
    is_url_source = (
        document.file_type in (DocumentType.YOUTUBE, DocumentType.WEB)
        and bool(document.source_url)
    )
    if not is_url_source and not storage.path_for(document.stored_name).is_file():
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


# Library filter groups shown to people, mapped to stored file types.
DOCUMENT_KINDS: dict[str, tuple[DocumentType, ...]] = {
    "documents": (
        DocumentType.PDF,
        DocumentType.DOCX,
        DocumentType.TXT,
        DocumentType.PPTX,
        DocumentType.XLSX,
        DocumentType.HTML,
    ),
    "images": (DocumentType.IMAGE,),
    "audio": (DocumentType.AUDIO,),
    "video": (DocumentType.VIDEO,),
    "links": (DocumentType.WEB, DocumentType.YOUTUBE),
}

# How many research titles to return per file in list responses.
USED_IN_LIMIT = 3


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
    kind: str | None = None,
) -> tuple[list[Document], int]:
    accessible_active = accessible_project_ids_select(user_id, include_archived=False)
    if project_id is not None:
        require_project_access(
            session, project_id, user_id, min_role=CollaboratorRole.VIEWER
        )
        filters = [Document.project_id == project_id]
    else:
        # Documents inside archived projects leave the global library too;
        # shared non-archived project documents appear for collaborators.
        filters = [
            or_(
                or_(
                    Document.user_id == user_id,
                    Document.project_id.in_(accessible_active),
                ),
            ),
            or_(
                Document.project_id.is_(None),
                Document.project_id.in_(accessible_active),
            ),
        ]
    normalized_search = search.strip() if search else None
    if normalized_search:
        filters.append(
            or_(
                Document.name.icontains(normalized_search, autoescape=True),
                Document.title.icontains(normalized_search, autoescape=True),
            )
        )
    if status is not None:
        filters.append(Document.status == status)
    if file_type is not None:
        filters.append(Document.file_type == file_type)
    if kind is not None:
        filters.append(Document.file_type.in_(DOCUMENT_KINDS[kind]))

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
    attach_document_usage(session, documents, user_id)
    return documents, total or 0


def attach_document_usage(
    session: Session, documents: list[Document], user_id: UUID
) -> None:
    """Set ``project_name`` and ``used_in`` on each document of a page.

    Two queries for the whole page: project names, then the research runs
    that were limited to these files.
    """
    if not documents:
        return
    accessible_projects = accessible_project_ids_select(user_id, include_archived=True)
    direct_research = select(ResearchMember.research_id).where(ResearchMember.user_id == user_id)
    project_ids = {doc.project_id for doc in documents if doc.project_id}
    names: dict[UUID, str] = {}
    if project_ids:
        names = dict(
            session.execute(
                select(ResearchProject.id, ResearchProject.name).where(
                    ResearchProject.id.in_(project_ids),
                    ResearchProject.id.in_(accessible_projects),
                )
            ).all()
        )
    usage: dict[UUID, list[dict[str, object]]] = {doc.id: [] for doc in documents}
    rows = session.execute(
        select(research_documents.c.document_id, Research.id, Research.title)
        .join(Research, Research.id == research_documents.c.research_id)
        .where(
            research_documents.c.document_id.in_(list(usage)),
            or_(
                Research.user_id == user_id,
                Research.id.in_(direct_research),
                Research.project_id.in_(accessible_projects),
            ),
            Research.archived_at.is_(None),
        )
        .order_by(Research.updated_at.desc())
    ).all()
    totals: dict[UUID, int] = {}
    for document_id, research_id, title in rows:
        totals[document_id] = totals.get(document_id, 0) + 1
        if len(usage[document_id]) < USED_IN_LIMIT:
            usage[document_id].append({"id": research_id, "title": title})
    for doc in documents:
        doc.project_name = names.get(doc.project_id) if doc.project_id else None
        doc.used_in = usage[doc.id]
        doc.used_in_count = totals.get(doc.id, 0)


def get_document(
    session: Session,
    document_id: UUID,
    user_id: UUID,
    *,
    min_role: CollaboratorRole = CollaboratorRole.VIEWER,
) -> Document:
    document, _ = require_document_access(
        session, document_id, user_id, min_role=min_role
    )
    return document


def delete_document(
    session: Session,
    document_id: UUID,
    storage: LocalDocumentStorage,
    user_id: UUID,
) -> None:
    document = get_document(
        session, document_id, user_id, min_role=CollaboratorRole.EDITOR
    )
    project_id = document.project_id
    doc_id = str(document.id)
    doc_name = document.name
    storage.delete(document.stored_name)
    session.delete(document)
    _commit(session, "The document metadata could not be deleted")
    if project_id is not None:
        publish_realtime_event(
            [project_room(project_id)],
            "document.deleted",
            {"projectId": str(project_id), "documentId": doc_id, "name": doc_name},
            actor=actor_for_user(session, user_id),
        )


def mark_interrupted(session: Session, document_id: UUID, message: str) -> None:
    """Flag a document whose processing never finished so the user can retry."""
    document = session.get(Document, document_id)
    if document is None or document.status == DocumentStatus.INDEXED:
        return
    document.status = DocumentStatus.FAILED
    document.processing_error = message[:1000]
    _commit(session, "The interrupted document could not be updated")
    _broadcast_document_event(session, document, "document.updated")
