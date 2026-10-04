"""Framework-neutral contracts for parsed research documents and nodes."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.documents import MetadataProvenance


class CanonicalMetadata(BaseModel):
    """Normalized source metadata without Docling or LlamaIndex objects."""

    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    doi: str | None = None
    openalex_id: str | None = None
    crossref_id: str | None = None
    publication_year: int | None = None
    published_at: datetime | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, MetadataProvenance] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ParsedNode(BaseModel):
    """One retrievable node ready for embedding and SQL persistence."""

    node_id: UUID
    text: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    section_path: list[str] = Field(default_factory=list)
    token_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ParsedDocument(BaseModel):
    """Result returned by an ingestion adapter at the framework boundary."""

    document_id: UUID
    metadata: CanonicalMetadata = Field(default_factory=CanonicalMetadata)
    page_count: int | None = Field(default=None, ge=0)
    parser_name: str
    parser_version: str | None = None
    ingestion_version: str
    nodes: list[ParsedNode]

    model_config = ConfigDict(extra="forbid")
