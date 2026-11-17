"""Discovery search annotation and SSRF-safe ingestion of curated external sources."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.models.document import Document
from app.schemas.discovery import (
    DiscoveredSourceCandidate,
    DiscoveryImportFailure,
    DiscoveryImportResponse,
    DiscoveryScope,
    DiscoverySearchResponse,
)
from app.services.discovery.providers import normalize_doi, search_curated_sources
from app.services.documents.records import _remove_document
from app.services.documents.storage import LocalDocumentStorage, R2DocumentStorage
from app.services.ingestion.pipeline import (
    DocumentIngestionError,
    _embed_nodes,
    _store_parsed_document,
    ingestion_adapter_for,
    stable_node_id,
)
from app.services.ingestion.web import WebsiteIngestionAdapter, chunk_web_sections, validate_public_url
from app.services.rag.embeddings import EmbeddingService
from app.services.research import projects as project_service

logger = logging.getLogger(__name__)


def _find_matching_document(
    session: Session,
    candidate: DiscoveredSourceCandidate,
    *,
    user_id: UUID,
    project_id: UUID | None,
) -> Document | None:
    conditions = []
    if candidate.doi:
        conditions.append(Document.doi == normalize_doi(candidate.doi))
    if candidate.openalex_id:
        conditions.append(Document.openalex_id == candidate.openalex_id)
    if candidate.crossref_id:
        conditions.append(Document.crossref_id == candidate.crossref_id)
    if candidate.url:
        conditions.append(Document.source_url == candidate.url)
    if candidate.open_access_pdf_url:
        conditions.append(Document.source_url == candidate.open_access_pdf_url)
    if not conditions:
        return None

    filters = [Document.user_id == user_id, or_(*conditions)]
    if project_id is None:
        filters.append(Document.project_id.is_(None))
    else:
        filters.append(Document.project_id == project_id)
    return session.scalar(select(Document).where(*filters).order_by(Document.created_at.desc()).limit(1))


def search_and_annotate(
    session: Session,
    *,
    user_id: UUID,
    query: str,
    scope: DiscoveryScope,
    limit: int,
    project_id: UUID | None,
    settings: Settings,
    client: httpx.Client | None = None,
) -> DiscoverySearchResponse:
    if not settings.discovery_enabled:
        raise AppError(
            "Controlled discovery is disabled in server configuration",
            status_code=503,
            code="discovery_disabled",
        )
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)

    outcome = search_curated_sources(
        query,
        scope=scope,
        limit=min(limit, settings.discovery_max_results),
        settings=settings,
        client=client,
    )
    annotated: list[DiscoveredSourceCandidate] = []
    for item in outcome.items:
        existing = _find_matching_document(session, item, user_id=user_id, project_id=project_id)
        if existing is not None and existing.status != DocumentStatus.FAILED:
            item = item.model_copy(
                update={
                    "already_in_library": True,
                    "existing_document_id": existing.id,
                }
            )
        annotated.append(item)

    return DiscoverySearchResponse(
        query=" ".join(query.split()).strip(),
        scope=scope,
        items=annotated,
        provider_errors=outcome.provider_errors,
    )


def _save_stored_bytes(
    storage: LocalDocumentStorage,
    payload: bytes,
    *,
    extension: str,
    content_type: str,
) -> tuple[str, str, str, int]:
    """Persist bytes locally (and upload to R2 when configured) without breaking storage bounds."""
    storage.root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    destination = storage._path_for(stored_name)
    destination.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    backend_name = storage.storage_backend_name

    if isinstance(storage, R2DocumentStorage):
        try:
            headers = storage._signed_headers(
                "PUT",
                stored_name,
                checksum,
                content_type=content_type,
            )
            response = storage._client.put(storage._object_url(stored_name), content=payload, headers=headers)
            if response.status_code not in {200, 201, 204}:
                raise AppError("Failed to persist discovered source in R2 storage", status_code=502, code="r2_upload_failed")
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    return stored_name, backend_name, checksum, len(payload)


def _download_open_access_pdf(
    pdf_url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    client: httpx.Client | None = None,
) -> bytes:
    target = validate_public_url(pdf_url)
    own_client = client is None
    active = client or httpx.Client(
        timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        follow_redirects=False,
    )
    try:
        headers = {
            "User-Agent": "AIResearchAssistant/1.0 (https://github.com/Santanu-SP/AI-Research-Assistant)",
            "Accept": "application/pdf",
        }
        response = active.get(target, headers=headers)
        for _ in range(3):
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            redirect_target = response.headers.get("location", "")
            target = validate_public_url(redirect_target)
            response = active.get(target, headers=headers)
        response.raise_for_status()
        content = response.content
    finally:
        if own_client:
            active.close()

    if not content or len(content) > max_bytes:
        raise DocumentIngestionError("Downloaded PDF exceeded size limit or was empty", code="invalid_pdf_signature")
    if b"%PDF-" not in content[:1024]:
        raise DocumentIngestionError("External link did not return a valid PDF document", code="invalid_pdf_signature")
    return content


def _parse_curated_abstract(
    candidate: DiscoveredSourceCandidate,
    *,
    document_id: UUID,
    ingestion_version: str,
    chunk_size: int,
    overlap: int,
) -> ParsedDocument:
    abstract_body = (candidate.abstract or "").strip()
    if len(abstract_body) < 20:
        raise DocumentIngestionError("Source has neither readable full text nor an abstract", code="empty_source_content")

    meta_lines = [f"Title: {candidate.title}"]
    if candidate.authors:
        meta_lines.append(f"Authors: {', '.join(candidate.authors[:8])}")
    if candidate.publication_year:
        meta_lines.append(f"Year: {candidate.publication_year}")
    if candidate.publisher:
        meta_lines.append(f"Publisher: {candidate.publisher}")
    if candidate.doi:
        meta_lines.append(f"DOI: {candidate.doi}")
    meta_lines.append("")
    meta_lines.append(abstract_body)
    full_block = "\n".join(meta_lines)

    section_name = "Overview" if candidate.provider == "wikipedia" else "Abstract"
    nodes = chunk_web_sections(
        document_id,
        [(section_name, full_block)],
        chunk_size=chunk_size,
        overlap=overlap,
        page_title=candidate.title,
        source_url=candidate.url,
    )
    if not nodes:
        node_id = stable_node_id(document_id, 0, full_block)
        nodes = [
            ParsedNode(
                node_id=node_id,
                text=full_block,
                chunk_index=0,
                page=1,
                page_end=1,
                section=section_name,
                section_path=[candidate.title, section_name],
                token_count=len(full_block.split()),
                metadata={"source_url": candidate.url, "content_kind": section_name.lower()},
            )
        ]

    provenance = {
        "title": MetadataProvenance.OPENALEX
        if candidate.provider == "openalex"
        else (MetadataProvenance.CROSSREF if candidate.provider == "crossref" else MetadataProvenance.EXTRACTED)
    }
    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=candidate.title,
            authors=candidate.authors or None,
            abstract=candidate.abstract,
            doi=normalize_doi(candidate.doi),
            openalex_id=candidate.openalex_id,
            crossref_id=candidate.crossref_id,
            publication_year=candidate.publication_year,
            values={
                "publisher": candidate.publisher,
                "citation_count": candidate.citation_count,
                "trust_tier": candidate.trust_tier,
                "discovery_provider": candidate.provider,
                "source_url": candidate.url,
            },
            provenance=provenance,
        ),
        page_count=1,
        parser_name=f"discovery-{candidate.provider}",
        parser_version="1.0",
        ingestion_version=f"{ingestion_version}:discovery",
        nodes=nodes,
    )


def _ingest_single_candidate(
    session: Session,
    candidate: DiscoveredSourceCandidate,
    *,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
    project_id: UUID | None,
    fetch_full_text: bool,
    embeddings: EmbeddingService | None,
    client: httpx.Client | None,
) -> tuple[Document, bool]:
    existing = _find_matching_document(session, candidate, user_id=user_id, project_id=project_id)
    if existing is not None and existing.status == DocumentStatus.FAILED:
        _remove_document(session, existing, storage)
        existing = None
    if existing is not None:
        return existing, True

    validated_url = validate_public_url(candidate.url)
    validated_pdf_url = validate_public_url(candidate.open_access_pdf_url) if candidate.open_access_pdf_url else None

    doc_id = uuid4()
    parsed: ParsedDocument | None = None
    file_type = DocumentType.WEB
    mime_type = "text/plain"
    content_level = (
        ContentLevel.WEB_PAGE
        if candidate.content_level == ContentLevel.WEB_PAGE
        else ContentLevel.ABSTRACT
    )
    extension = ".web"
    raw_bytes = validated_url.encode("utf-8")

    # 1. Try Open-Access PDF when explicitly available
    if fetch_full_text and validated_pdf_url:
        try:
            pdf_bytes = _download_open_access_pdf(
                validated_pdf_url,
                max_bytes=settings.document_max_upload_bytes,
                timeout_seconds=settings.discovery_timeout_seconds,
                client=client,
            )
            tmp_pdf = storage.root / f"_tmp_{doc_id.hex}.pdf"
            storage.root.mkdir(parents=True, exist_ok=True)
            tmp_pdf.write_bytes(pdf_bytes)
            try:
                parsed = ingestion_adapter_for(settings).parse(
                    tmp_pdf,
                    document_id=doc_id,
                    ingestion_version=settings.ingestion_version,
                )
            finally:
                tmp_pdf.unlink(missing_ok=True)
            if parsed and parsed.nodes:
                file_type = DocumentType.PDF
                mime_type = "application/pdf"
                content_level = ContentLevel.FULL_TEXT
                extension = ".pdf"
                raw_bytes = pdf_bytes
        except Exception as exc:
            logger.info("OA PDF fetch/parse skipped for %s (%s); falling back cleanly", candidate.title, exc)
            parsed = None

    # 2. Try curated Web article / Wikipedia extraction when PDF wasn't obtained
    if parsed is None and fetch_full_text and (candidate.provider == "wikipedia" or not candidate.abstract):
        try:
            web_adapter = WebsiteIngestionAdapter(
                jina_reader_base_url=settings.jina_reader_base_url,
                jina_api_key=settings.jina_api_key,
                chunk_size=settings.document_chunk_size,
                overlap=settings.document_chunk_overlap,
                client=client,
            )
            parsed = web_adapter.parse_url(
                validated_url,
                document_id=doc_id,
                ingestion_version=settings.ingestion_version,
            )
            content_level = ContentLevel.WEB_PAGE
        except Exception as exc:
            logger.info("Web fetch skipped for %s (%s); trying curated abstract", validated_url, exc)
            parsed = None

    # 3. Fall back cleanly to curated scholarly abstract / Wikipedia summary
    if parsed is None:
        parsed = _parse_curated_abstract(
            candidate,
            document_id=doc_id,
            ingestion_version=settings.ingestion_version,
            chunk_size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )
        content_level = (
            ContentLevel.WEB_PAGE
            if candidate.provider == "wikipedia"
            else ContentLevel.ABSTRACT
        )

    stored_name, backend_name, checksum, size = _save_stored_bytes(
        storage,
        raw_bytes,
        extension=extension,
        content_type=mime_type,
    )

    display_name = (candidate.title or validated_url)[:255]
    document = Document(
        id=doc_id,
        user_id=user_id,
        project_id=project_id,
        name=display_name,
        stored_name=stored_name,
        storage_backend=backend_name,
        file_type=file_type,
        mime_type=mime_type,
        size=size,
        source_type=candidate.source_type,
        source_uri=validated_pdf_url or validated_url,
        source_url=validated_url,
        content_level=content_level,
        checksum=checksum,
        status=DocumentStatus.PROCESSING,
    )
    session.add(document)

    try:
        vectors, emb_model, emb_version = _embed_nodes(session, document, parsed, settings, embeddings)
        _store_parsed_document(
            document,
            parsed,
            vectors,
            embedding_model=emb_model,
            embedding_version=emb_version,
        )
        # Preserve authoritative bibliographic metadata from the curated provider.
        document.title = candidate.title[:1000]
        document.authors = candidate.authors or parsed.metadata.authors
        document.abstract = candidate.abstract or parsed.metadata.abstract
        document.doi = normalize_doi(candidate.doi) or parsed.metadata.doi
        document.openalex_id = candidate.openalex_id or parsed.metadata.openalex_id
        document.crossref_id = candidate.crossref_id or parsed.metadata.crossref_id
        document.publication_year = candidate.publication_year or parsed.metadata.publication_year
        document.canonical_metadata = {
            **(document.canonical_metadata or {}),
            "publisher": candidate.publisher,
            "citation_count": candidate.citation_count,
            "trust_tier": candidate.trust_tier,
            "discovery_provider": candidate.provider,
            "source_url": validated_url,
        }
        document.content_level = content_level
        session.commit()
        session.refresh(document)
        return document, False
    except Exception:
        session.rollback()
        try:
            storage.delete(stored_name)
        except Exception:
            pass
        raise


def import_discovered_sources(
    session: Session,
    candidates: list[DiscoveredSourceCandidate],
    *,
    storage: LocalDocumentStorage,
    settings: Settings,
    user_id: UUID,
    project_id: UUID | None = None,
    fetch_full_text: bool = True,
    embeddings: EmbeddingService | None = None,
    client: httpx.Client | None = None,
) -> DiscoveryImportResponse:
    if not settings.discovery_enabled:
        raise AppError(
            "Controlled discovery is disabled in server configuration",
            status_code=503,
            code="discovery_disabled",
        )
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)

    documents: list[Document] = []
    reused_count = 0
    imported_count = 0
    failed: list[DiscoveryImportFailure] = []

    for candidate in candidates:
        try:
            doc, was_reused = _ingest_single_candidate(
                session,
                candidate,
                storage=storage,
                settings=settings,
                user_id=user_id,
                project_id=project_id,
                fetch_full_text=fetch_full_text,
                embeddings=embeddings,
                client=client,
            )
            documents.append(doc)
            if was_reused:
                reused_count += 1
            else:
                imported_count += 1
        except (AppError, DocumentIngestionError) as exc:
            failed.append(
                DiscoveryImportFailure(
                    title=candidate.title,
                    url=candidate.url,
                    reason=str(exc),
                )
            )
        except Exception as exc:
            logger.warning("Unexpected failure importing %s: %s", candidate.url, exc, exc_info=True)
            failed.append(
                DiscoveryImportFailure(
                    title=candidate.title,
                    url=candidate.url,
                    reason="The discovered source could not be processed.",
                )
            )

    return DiscoveryImportResponse(
        documents=documents,
        reused_count=reused_count,
        imported_count=imported_count,
        failed=failed,
    )
