"""Canonical ingestion orchestration over framework-neutral parsed documents."""

from collections.abc import Callable
from hashlib import sha256
import logging
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus
from app.domain.ingestion import ParsedDocument
from app.models.document import Document, DocumentChunk
from app.services.embeddings import EmbeddingService, embedding_service_for


logger = logging.getLogger(__name__)


class DocumentIngestionError(Exception):
    """Safe parser or normalization failure suitable for an API response."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "document_processing_failed",
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class DocumentIngestionAdapter(Protocol):
    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument: ...


def stable_node_id(document_id: UUID, index: int, text: str) -> UUID:
    """Build a repeatable node UUID from identity, order, and content."""

    fingerprint = sha256(text.encode("utf-8")).hexdigest()
    return uuid5(NAMESPACE_URL, f"ara:{document_id}:{index}:{fingerprint}")


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


def ingestion_adapter_for(settings: Settings) -> DocumentIngestionAdapter:
    if settings.document_ingestion_backend == "legacy":
        from app.services.legacy_ingestion import LegacyPdfIngestionAdapter

        return LegacyPdfIngestionAdapter(settings)

    from app.services.docling_ingestion import docling_adapter_for

    return docling_adapter_for(settings)


def _failure_details(exc: Exception) -> tuple[str, int, str]:
    if isinstance(exc, AppError):
        return str(exc), exc.status_code, exc.code
    if isinstance(exc, DocumentIngestionError):
        return str(exc), exc.status_code, exc.code
    return "Document ingestion failed", 422, "document_processing_failed"


async def ingest_document(
    session: Session,
    document: Document,
    path: Path,
    settings: Settings,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    clock: Callable[[], float] = perf_counter,
) -> Document:
    """Parse, embed, and atomically publish one stored document."""

    active_adapter = adapter or ingestion_adapter_for(settings)
    started = clock()
    document.status = DocumentStatus.PROCESSING
    document.processing_error = None
    _commit(session, "The document processing status could not be saved")

    try:
        parse_started = clock()
        parsed = await run_in_threadpool(
            active_adapter.parse,
            path,
            document_id=document.id,
            ingestion_version=settings.ingestion_version,
        )
        parse_ms = round((clock() - parse_started) * 1000, 2)
        if not parsed.nodes:
            raise DocumentIngestionError(
                "The document contains no retrievable text or tables"
            )
        if parsed.document_id != document.id:
            raise DocumentIngestionError(
                "The parser returned a mismatched document identity"
            )

        embedding_started = clock()
        vectors: list[list[float] | None] = [None] * len(parsed.nodes)
        if settings.embedding_enabled:
            if (
                embeddings is None
                and (session.bind is None or session.bind.dialect.name != "postgresql")
            ):
                raise AppError(
                    "Document indexing requires PostgreSQL with pgvector",
                    status_code=503,
                    code="embedding_backend_unavailable",
                )
            embedding_service = embeddings or embedding_service_for(settings)
            generated = embedding_service.embed_documents(
                [node.text for node in parsed.nodes]
            )
            if len(generated) != len(parsed.nodes):
                raise AppError(
                    "Embedding generation returned an invalid batch",
                    status_code=500,
                    code="embedding_batch_mismatch",
                )
            vectors = generated
        embedding_ms = round((clock() - embedding_started) * 1000, 2)

        persistence_started = clock()
        canonical = parsed.metadata
        document.title = canonical.title
        document.authors = canonical.authors
        document.abstract = canonical.abstract
        document.doi = canonical.doi
        document.openalex_id = canonical.openalex_id
        document.crossref_id = canonical.crossref_id
        document.publication_year = canonical.publication_year
        document.published_at = canonical.published_at
        document.canonical_metadata = canonical.values or None
        document.metadata_provenance = (
            {key: value.value for key, value in canonical.provenance.items()}
            or None
        )
        document.page_count = parsed.page_count
        document.parser_name = parsed.parser_name
        document.parser_version = parsed.parser_version
        document.ingestion_version = parsed.ingestion_version
        document.chunks = []
        for node, vector in zip(parsed.nodes, vectors, strict=True):
            node_metadata = {
                **node.metadata,
                "document_id": str(document.id),
                "project_id": str(document.project_id)
                if document.project_id
                else None,
                "source_type": document.source_type.value,
                "content_level": document.content_level.value,
                "title": canonical.title or document.name,
                "parser_name": parsed.parser_name,
                "ingestion_version": parsed.ingestion_version,
            }
            document.chunks.append(
                DocumentChunk(
                    id=node.node_id,
                    node_id=str(node.node_id),
                    document_id=document.id,
                    text=node.text,
                    page=node.page,
                    page_end=node.page_end,
                    section=node.section,
                    section_path=node.section_path or None,
                    chunk_index=node.chunk_index,
                    token_count=node.token_count,
                    node_metadata=node_metadata,
                    embedding=vector,
                )
            )
        document.status = DocumentStatus.INDEXED
        document.processing_error = None
        _commit(session, "The processed document could not be saved")
        session.refresh(document)
        persistence_ms = round((clock() - persistence_started) * 1000, 2)
        logger.info(
            "Document ingestion completed",
            extra={
                "user_id": str(document.user_id),
                "project_id": str(document.project_id)
                if document.project_id
                else None,
                "document_id": str(document.id),
                "parser_name": parsed.parser_name,
                "source_type": document.source_type.value,
                "parse_ms": parse_ms,
                "embedding_ms": embedding_ms,
                "persistence_ms": persistence_ms,
                "total_ingestion_ms": round((clock() - started) * 1000, 2),
                "node_count": len(parsed.nodes),
            },
        )
        return document
    except Exception as exc:
        session.rollback()
        message, status_code, code = _failure_details(exc)
        failed = session.get(Document, document.id)
        if failed is None:
            raise AppError(
                "The document processing failure could not be recorded",
                status_code=500,
                code="document_persistence_error",
            ) from exc
        failed.chunks.clear()
        failed.status = DocumentStatus.FAILED
        failed.processing_error = message[:1000]
        _commit(session, "The document processing failure could not be saved")
        logger.exception(
            "Document ingestion failed",
            extra={
                "user_id": str(failed.user_id),
                "project_id": str(failed.project_id)
                if failed.project_id
                else None,
                "document_id": str(failed.id),
                "source_type": failed.source_type.value,
                "total_ingestion_ms": round((clock() - started) * 1000, 2),
            },
        )
        raise AppError(message, status_code=status_code, code=code) from exc
