from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.schemas.base import ApiSchema


class DocumentResponse(ApiSchema):
    id: UUID
    project_id: UUID | None = None
    name: str
    file_type: DocumentType = Field(serialization_alias="type")
    mime_type: str
    size: int = Field(ge=0)
    source_type: SourceType
    source_uri: str | None
    source_url: str | None
    content_level: ContentLevel
    status: DocumentStatus
    ingestion_status: DocumentStatus
    title: str | None
    authors: list[str] | None
    abstract: str | None
    doi: str | None
    openalex_id: str | None
    crossref_id: str | None
    publication_year: int | None
    published_at: datetime | None
    canonical_metadata: dict[str, object] | None
    metadata_provenance: dict[str, str] | None
    parser_name: str | None
    parser_version: str | None
    ingestion_version: str | None
    page_count: int | None = Field(default=None, ge=0)
    uploaded_at: datetime
    processing_error: str | None
    chunk_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(ApiSchema):
    items: list[DocumentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class DocumentChunkResponse(ApiSchema):
    id: UUID = Field(serialization_alias="chunkId")
    document_id: UUID
    text: str
    node_id: str
    page: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None
    section_path: list[str] | None
    chunk_index: int = Field(ge=0)
    token_count: int | None = Field(default=None, ge=0)
    node_metadata: dict[str, object] | None
