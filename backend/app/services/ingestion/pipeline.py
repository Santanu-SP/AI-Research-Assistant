"""Canonical ingestion orchestration over framework-neutral parsed documents."""

from collections.abc import Callable
from hashlib import sha256
import logging
from pathlib import Path
from time import perf_counter
from typing import NoReturn, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus, DocumentType
from app.domain.ingestion import ParsedDocument
from app.models.document import Document, DocumentChunk
from app.services.rag.embeddings import (
    EmbeddingService,
    active_embedding_model_identity,
    embedding_service_for,
)


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
        from app.services.ingestion.legacy import LegacyPdfIngestionAdapter

        logger.warning(
            "Using the explicitly configured legacy pypdf ingestion fallback"
        )
        return LegacyPdfIngestionAdapter(settings)

    from app.services.ingestion.docling import docling_adapter_for

    return docling_adapter_for(settings)


class _MultimodalAdapterWrapper:
    """Routes specialized document/media formats into the unified ParsedDocument pipeline."""

    def __init__(self, document: Document, settings: Settings) -> None:
        self.document = document
        self.settings = settings

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        ft = self.document.file_type
        if ft == DocumentType.YOUTUBE:
            from app.services.ingestion.youtube import YouTubeIngestionAdapter

            yt = YouTubeIngestionAdapter(chunk_size_chars=min(self.settings.document_chunk_size, 1500))
            url = self.document.source_url or path.read_text(encoding="utf-8").strip()
            return yt.parse_url(url, document_id=document_id, ingestion_version=ingestion_version)

        if ft == DocumentType.WEB:
            from app.services.ingestion.web import WebsiteIngestionAdapter

            web = WebsiteIngestionAdapter(
                jina_reader_base_url=self.settings.jina_reader_base_url,
                jina_api_key=self.settings.jina_api_key,
                chunk_size=self.settings.document_chunk_size,
                overlap=self.settings.document_chunk_overlap,
            )
            url = self.document.source_url or path.read_text(encoding="utf-8").strip()
            return web.parse_url(url, document_id=document_id, ingestion_version=ingestion_version)

        if ft == DocumentType.AUDIO:
            from app.services.ingestion.audio import audio_transcriber_for

            transcriber = audio_transcriber_for(self.settings)
            return transcriber.parse(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                original_name=self.document.name,
            )

        if ft == DocumentType.VIDEO:
            from app.services.ingestion.video import video_adapter_for

            video_adapter = video_adapter_for(self.settings)
            return video_adapter.parse(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                original_name=self.document.name,
            )

        if ft == DocumentType.IMAGE:
            from app.services.ingestion.vision import vision_analyzer_for

            analyzer = vision_analyzer_for(self.settings)
            return analyzer.parse_image_document(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                mime_type=self.document.mime_type,
                original_name=self.document.name,
            )

        if ft == DocumentType.PPTX:
            from app.services.ingestion.office_html import parse_pptx_document

            return parse_pptx_document(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                chunk_size=self.settings.document_chunk_size,
            )

        if ft == DocumentType.XLSX:
            from app.services.ingestion.office_html import parse_xlsx_document

            return parse_xlsx_document(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
            )

        if ft == DocumentType.HTML:
            from app.services.ingestion.office_html import parse_html_document

            return parse_html_document(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                chunk_size=self.settings.document_chunk_size,
                overlap=self.settings.document_chunk_overlap,
            )

        return ingestion_adapter_for(self.settings).parse(
            path,
            document_id=document_id,
            ingestion_version=ingestion_version,
        )


def _resolve_adapter(
    document: Document,
    settings: Settings,
    explicit_adapter: DocumentIngestionAdapter | None,
) -> DocumentIngestionAdapter:
    if explicit_adapter is not None:
        return explicit_adapter
    if document.file_type in {
        DocumentType.YOUTUBE,
        DocumentType.WEB,
        DocumentType.AUDIO,
        DocumentType.VIDEO,
        DocumentType.IMAGE,
        DocumentType.PPTX,
        DocumentType.XLSX,
        DocumentType.HTML,
    }:
        return _MultimodalAdapterWrapper(document, settings)
    return ingestion_adapter_for(settings)


def _failure_details(exc: Exception) -> tuple[str, int, str]:
    if isinstance(exc, AppError):
        return str(exc), exc.status_code, exc.code
    if isinstance(exc, DocumentIngestionError):
        return str(exc), exc.status_code, exc.code
    return "Document ingestion failed", 422, "document_processing_failed"


def _elapsed_ms(clock: Callable[[], float], started: float) -> float:
    return round((clock() - started) * 1000, 2)


def _project_label(document: Document) -> str | None:
    if document.project_id is None:
        return None
    return str(document.project_id)


def _parse_uploaded_document(
    adapter: DocumentIngestionAdapter,
    path: Path,
    document: Document,
    settings: Settings,
) -> ParsedDocument:
    parsed = adapter.parse(
        path,
        document_id=document.id,
        ingestion_version=settings.ingestion_version,
    )
    if not parsed.nodes:
        raise DocumentIngestionError(
            "The document contains no retrievable text or tables"
        )
    if parsed.document_id != document.id:
        raise DocumentIngestionError(
            "The parser returned a mismatched document identity"
        )
    return parsed


def _embed_nodes(
    session: Session,
    document: Document,
    parsed: ParsedDocument,
    settings: Settings,
    embeddings: EmbeddingService | None,
) -> tuple[list[list[float] | None], str | None, str | None]:
    vectors: list[list[float] | None] = [None] * len(parsed.nodes)
    if not settings.embedding_enabled:
        return vectors, None, None

    dialect = None if session.bind is None else session.bind.dialect.name
    if (
        embeddings is None
        and dialect != "postgresql"
        and not settings.allow_sqlite_retrieval_fallback
        and settings.embedding_provider == "local"
    ):
        raise AppError(
            "Document indexing requires PostgreSQL with pgvector",
            status_code=503,
            code="embedding_backend_unavailable",
        )

    embedding_service = embeddings or embedding_service_for(settings)
    model_name, model_version = active_embedding_model_identity(settings, embedding_service)

    # Reuse existing vectors when re-processing identical chunks with the same embedding model
    if (
        document.embedding_model == model_name
        and document.embedding_version == model_version
        and document.chunks
    ):
        existing_by_node_id = {
            chunk.node_id: list(chunk.embedding)
            for chunk in document.chunks
            if chunk.embedding is not None
        }
        if existing_by_node_id and all(
            str(node.node_id) in existing_by_node_id for node in parsed.nodes
        ):
            return (
                [existing_by_node_id[str(node.node_id)] for node in parsed.nodes],
                model_name,
                model_version,
            )

    generated = embedding_service.embed_documents(
        [node.text for node in parsed.nodes]
    )
    if len(generated) != len(parsed.nodes):
        raise AppError(
            "Embedding generation returned an invalid batch",
            status_code=500,
            code="embedding_batch_mismatch",
        )
    return generated, model_name, model_version


def _store_parsed_document(
    document: Document,
    parsed: ParsedDocument,
    vectors: list[list[float] | None],
    *,
    embedding_model: str | None = None,
    embedding_version: str | None = None,
) -> None:
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
    provenance = {
        key: value.value for key, value in canonical.provenance.items()
    }
    document.metadata_provenance = provenance or None
    document.page_count = parsed.page_count
    document.parser_name = parsed.parser_name
    document.parser_version = parsed.parser_version
    document.ingestion_version = parsed.ingestion_version
    document.embedding_model = embedding_model
    document.embedding_version = embedding_version
    document.chunks = []
    for node, vector in zip(parsed.nodes, vectors, strict=True):
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
                node_metadata={
                    **node.metadata,
                    "document_id": str(document.id),
                    "project_id": _project_label(document),
                    "source_type": document.source_type.value,
                    "content_level": document.content_level.value,
                    "title": canonical.title or document.name,
                    "parser_name": parsed.parser_name,
                    "ingestion_version": parsed.ingestion_version,
                    "embedding_model": embedding_model,
                    "embedding_version": embedding_version,
                },
                embedding=vector,
            )
        )
    document.status = DocumentStatus.INDEXED
    document.processing_error = None


def reembed_document(
    session: Session,
    document: Document,
    settings: Settings,
    embeddings: EmbeddingService | None = None,
    *,
    force: bool = False,
) -> Document:
    """Controlled re-embedding for an indexed document without re-parsing the file."""
    if not document.chunks:
        return document
    embedding_service = embeddings or embedding_service_for(settings)
    model_name, model_version = active_embedding_model_identity(settings, embedding_service)
    if (
        not force
        and document.embedding_model == model_name
        and document.embedding_version == model_version
        and all(chunk.embedding is not None for chunk in document.chunks)
    ):
        return document

    texts = [chunk.text for chunk in document.chunks]
    vectors = embedding_service.embed_documents(texts)
    if len(vectors) != len(document.chunks):
        raise AppError(
            "Embedding generation returned an invalid batch",
            status_code=500,
            code="embedding_batch_mismatch",
        )
    for chunk, vec in zip(document.chunks, vectors, strict=True):
        chunk.embedding = vec
        meta = dict(chunk.node_metadata or {})
        meta["embedding_model"] = model_name
        meta["embedding_version"] = model_version
        chunk.node_metadata = meta
    document.embedding_model = model_name
    document.embedding_version = model_version
    _commit(session, "The updated document embeddings could not be saved")
    session.refresh(document)
    return document


def _record_ingestion_failure(
    session: Session,
    document: Document,
    exc: Exception,
    started: float,
    clock: Callable[[], float],
) -> NoReturn:
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
            "project_id": _project_label(failed),
            "document_id": str(failed.id),
            "source_type": failed.source_type.value,
            "total_ingestion_ms": _elapsed_ms(clock, started),
        },
    )
    raise AppError(message, status_code=status_code, code=code) from exc


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
    """Run :func:`process_document` on a worker thread."""
    return await run_in_threadpool(
        process_document,
        session,
        document,
        path,
        settings,
        adapter=adapter,
        embeddings=embeddings,
        clock=clock,
    )


def process_document(
    session: Session,
    document: Document,
    path: Path,
    settings: Settings,
    *,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
    clock: Callable[[], float] = perf_counter,
) -> Document:
    """Parse, embed, and atomically publish one stored document (blocking)."""

    active_adapter = _resolve_adapter(document, settings, adapter)
    started = clock()
    document.status = DocumentStatus.PROCESSING
    document.processing_error = None
    _commit(session, "The document processing status could not be saved")

    try:
        parse_started = clock()
        parsed = _parse_uploaded_document(
            active_adapter,
            path,
            document,
            settings,
        )
        parse_ms = _elapsed_ms(clock, parse_started)

        embedding_started = clock()
        vectors, emb_model, emb_version = _embed_nodes(
            session, document, parsed, settings, embeddings
        )
        embedding_ms = _elapsed_ms(clock, embedding_started)

        persistence_started = clock()
        _store_parsed_document(
            document,
            parsed,
            vectors,
            embedding_model=emb_model,
            embedding_version=emb_version,
        )
        _commit(session, "The processed document could not be saved")
        session.refresh(document)
        persistence_ms = _elapsed_ms(clock, persistence_started)
        logger.info(
            "Document ingestion completed",
            extra={
                "user_id": str(document.user_id),
                "project_id": _project_label(document),
                "document_id": str(document.id),
                "parser_name": parsed.parser_name,
                "source_type": document.source_type.value,
                "parse_ms": parse_ms,
                "embedding_ms": embedding_ms,
                "persistence_ms": persistence_ms,
                "total_ingestion_ms": _elapsed_ms(clock, started),
                "node_count": len(parsed.nodes),
            },
        )
        return document
    except Exception as exc:
        _record_ingestion_failure(session, document, exc, started, clock)
