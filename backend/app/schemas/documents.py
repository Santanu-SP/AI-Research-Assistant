from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.domain.documents import DocumentStatus, DocumentType
from app.schemas.base import ApiSchema


class DocumentResponse(ApiSchema):
    id: UUID
    name: str
    file_type: DocumentType = Field(serialization_alias="type")
    mime_type: str
    size: int = Field(ge=0)
    status: DocumentStatus
    title: str | None
    authors: list[str] | None
    doi: str | None
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
    page: int = Field(ge=1)
    section: str | None
    chunk_index: int = Field(ge=0)
