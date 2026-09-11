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
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(ApiSchema):
    items: list[DocumentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
