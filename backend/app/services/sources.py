"""Project-owned URL and scholarly source ingestion."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import (
    ContentLevel,
    DocumentStatus,
    DocumentType,
    MetadataProvenance,
    SourceType,
)
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.domain.scholarly import ResolutionStatus, ScholarlyWorkMetadata
from app.models.document import Document
from app.services.doi import normalize_doi
from app.services.embeddings import EmbeddingService
from app.services.ingestion import (
    DocumentIngestionAdapter,
    ingest_document,
    ingest_parsed_document,
    ingestion_adapter_for,
    stable_node_id,
)
from app.services.projects import get_project
from app.services.scholarly import DoiResolver, provider_clients
from app.services.scholarly_providers import ProviderError
from app.services.storage import LocalDocumentStorage, SUPPORTED_DOCUMENT_TYPES
from app.services.url_fetch import SecureUrlFetcher


def _commit(session: Session, message: str) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(message, status_code=500, code="source_persistence_error") from exc


def _scope_filters(user_id: UUID, project_id: UUID) -> list[object]:
    return [Document.user_id == user_id, Document.project_id == project_id]


def _duplicate_checksum(
    session: Session, user_id: UUID, project_id: UUID, checksum: str
) -> Document | None:
    return session.scalar(
        select(Document).where(
            *_scope_filters(user_id, project_id),
            Document.checksum == checksum,
        )
    )


def _duplicate_doi(
    session: Session, user_id: UUID, project_id: UUID, doi: str
) -> Document | None:
    return session.scalar(
        select(Document).where(
            *_scope_filters(user_id, project_id),
            func.lower(Document.doi) == doi,
        )
    )


def _raise_duplicate() -> None:
    raise AppError(
        "This source already exists in the project",
        status_code=409,
        code="duplicate_source",
    )


class _RemoteMetadataAdapter:
    def __init__(
        self,
        delegate: DocumentIngestionAdapter,
        *,
        source_url: str,
        fetched_at: datetime,
    ) -> None:
        self.delegate = delegate
        self.source_url = source_url
        self.fetched_at = fetched_at

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        parsed = self.delegate.parse(
            path,
            document_id=document_id,
            ingestion_version=ingestion_version,
        )
        parsed.metadata.values = {
            **parsed.metadata.values,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(),
        }
        parsed.metadata.provenance["source_url"] = MetadataProvenance.EXTRACTED
        return parsed


def _remote_name(url: str, extension: str) -> str:
    basename = Path(urlsplit(url).path).name
    basename = re.sub(r"[^A-Za-z0-9._ -]+", "-", basename).strip(" .-")
    if not basename:
        basename = f"web-source{extension}"
    if Path(basename).suffix.casefold() != extension:
        basename = f"{basename[:220]}{extension}"
    return basename[:255]


async def create_url_source(
    session: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    url: str,
    storage: LocalDocumentStorage,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    fetcher: SecureUrlFetcher | None = None,
    adapter: DocumentIngestionAdapter | None = None,
    embeddings: EmbeddingService | None = None,
) -> Document:
    get_project(session, project_id, user_id)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
    try:
        active_fetcher = fetcher or SecureUrlFetcher(
            active_client,
            timeout=settings.url_fetch_timeout,
            connect_timeout=settings.url_connect_timeout,
            max_bytes=min(settings.url_max_bytes, settings.document_max_upload_bytes),
            max_redirects=settings.url_max_redirects,
        )
        fetched = await active_fetcher.fetch(url)
    finally:
        if owns_client:
            await active_client.aclose()

    stored = storage.save_content(fetched.content, fetched.extension)
    if _duplicate_checksum(session, user_id, project_id, stored.checksum):
        storage.delete(stored.stored_name)
        _raise_duplicate()
    file_type = SUPPORTED_DOCUMENT_TYPES[fetched.extension][0]
    fetched_at = datetime.now(UTC)
    document = Document(
        user_id=user_id,
        project_id=project_id,
        name=_remote_name(fetched.final_url, fetched.extension),
        stored_name=stored.stored_name,
        file_type=file_type,
        mime_type=fetched.content_type,
        size=stored.size,
        source_type=SourceType.WEB_PAGE,
        source_uri=url.strip(),
        source_url=fetched.final_url,
        checksum=stored.checksum,
        content_level=(
            ContentLevel.FULL_TEXT
            if file_type is DocumentType.PDF
            else ContentLevel.WEB_PAGE
        ),
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    try:
        _commit(session, "The URL source could not be saved")
        session.refresh(document)
    except AppError:
        storage.delete(stored.stored_name)
        raise
    wrapped = _RemoteMetadataAdapter(
        adapter or ingestion_adapter_for(settings),
        source_url=fetched.final_url,
        fetched_at=fetched_at,
    )
    return await ingest_document(
        session,
        document,
        storage.path_for(stored.stored_name),
        settings,
        adapter=wrapped,
        embeddings=embeddings,
    )


def _canonical_scholarly(
    metadata: ScholarlyWorkMetadata,
    status: ResolutionStatus,
) -> CanonicalMetadata:
    values = {
        "journal": metadata.journal,
        "publisher": metadata.publisher,
        "landing_url": metadata.landing_url,
        "open_access_status": metadata.open_access_status,
        "provider_metadata": metadata.provider_metadata,
        "metadata_conflicts": [item.model_dump(mode="json") for item in metadata.conflicts],
        "resolution_status": status.value,
    }
    return CanonicalMetadata(
        title=metadata.title,
        authors=metadata.authors,
        abstract=metadata.abstract,
        doi=metadata.doi,
        openalex_id=metadata.openalex_id,
        crossref_id=metadata.crossref_id,
        publication_year=metadata.publication_year,
        published_at=metadata.published_at,
        values={key: value for key, value in values.items() if value is not None},
        provenance=metadata.field_provenance,
    )


async def _store_scholarly_source(
    session: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    source_type: SourceType,
    metadata: ScholarlyWorkMetadata,
    resolution_status: ResolutionStatus,
    settings: Settings,
    embeddings: EmbeddingService | None,
) -> Document:
    doi = metadata.doi
    if doi and _duplicate_doi(session, user_id, project_id, doi):
        _raise_duplicate()
    document_id = uuid4()
    source_identifier = doi or metadata.openalex_id or str(document_id)
    has_abstract = bool(metadata.abstract)
    document = Document(
        id=document_id,
        user_id=user_id,
        project_id=project_id,
        name=metadata.title or source_identifier,
        stored_name=f"metadata-{document_id}.json",
        file_type=DocumentType.METADATA,
        mime_type="application/vnd.ai-research-assistant.scholarly+json",
        size=0,
        source_type=source_type,
        source_uri=(f"https://doi.org/{doi}" if doi else metadata.landing_url),
        source_url=metadata.landing_url,
        checksum=sha256(f"{source_type.value}:{source_identifier}".encode()).hexdigest(),
        content_level=(ContentLevel.ABSTRACT if has_abstract else ContentLevel.METADATA_ONLY),
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    _commit(session, "The scholarly source could not be saved")
    session.refresh(document)
    nodes: list[ParsedNode] = []
    if metadata.abstract:
        nodes.append(
            ParsedNode(
                node_id=stable_node_id(document.id, 0, metadata.abstract),
                text=metadata.abstract,
                chunk_index=0,
                section="Abstract",
                section_path=["Abstract"],
                metadata={"content_kind": "abstract", "evidence_scope": "abstract"},
            )
        )
    parsed = ParsedDocument(
        document_id=document.id,
        metadata=_canonical_scholarly(metadata, resolution_status),
        parser_name="scholarly-metadata",
        parser_version="1",
        ingestion_version="scholarly-metadata-v1",
        nodes=nodes,
    )
    return await ingest_parsed_document(
        session,
        document,
        parsed,
        settings,
        embeddings=embeddings,
        allow_empty=True,
    )


async def create_doi_source(
    session: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    doi: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    embeddings: EmbeddingService | None = None,
) -> Document:
    get_project(session, project_id, user_id)
    normalized = normalize_doi(doi)
    if _duplicate_doi(session, user_id, project_id, normalized):
        _raise_duplicate()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
    try:
        crossref, openalex = provider_clients(settings, active_client)
        resolution = await DoiResolver(crossref, openalex).resolve(normalized)
    finally:
        if owns_client:
            await active_client.aclose()
    if resolution.metadata is None:
        if resolution.status is ResolutionStatus.PROVIDER_UNAVAILABLE:
            raise AppError(
                "Scholarly metadata providers are temporarily unavailable",
                status_code=503,
                code="metadata_providers_unavailable",
            )
        raise AppError(
            "The DOI could not be resolved by Crossref or OpenAlex",
            status_code=404,
            code="doi_unresolved",
        )
    return await _store_scholarly_source(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=SourceType.DOI,
        metadata=resolution.metadata,
        resolution_status=resolution.status,
        settings=settings,
        embeddings=embeddings,
    )


async def create_provider_source(
    session: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    source_type: SourceType,
    identifier: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    embeddings: EmbeddingService | None = None,
) -> Document:
    get_project(session, project_id, user_id)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
    try:
        crossref, openalex = provider_clients(settings, active_client)
        if source_type is SourceType.CROSSREF:
            doi = normalize_doi(identifier)
            if _duplicate_doi(session, user_id, project_id, doi):
                _raise_duplicate()
            metadata = await crossref.lookup_doi(doi)
        elif source_type is SourceType.OPENALEX:
            metadata = await openalex.lookup_work(identifier)
            if metadata and metadata.doi and _duplicate_doi(
                session, user_id, project_id, metadata.doi
            ):
                _raise_duplicate()
        else:
            raise AppError("Unsupported scholarly provider", status_code=422)
    except ProviderError as exc:
        raise AppError(str(exc), status_code=exc.status_code, code=exc.code) from exc
    finally:
        if owns_client:
            await active_client.aclose()
    if metadata is None:
        raise AppError(
            "The scholarly work could not be resolved",
            status_code=404,
            code="scholarly_work_unresolved",
        )
    return await _store_scholarly_source(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        metadata=metadata,
        resolution_status=ResolutionStatus.RESOLVED,
        settings=settings,
        embeddings=embeddings,
    )
