"""Provider-neutral scholarly metadata and resolution contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.documents import MetadataProvenance


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONFLICTING_METADATA = "conflicting_metadata"


class MetadataConflict(BaseModel):
    field: str
    values: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class ScholarlyWorkMetadata(BaseModel):
    """Canonical result produced by one provider or a deterministic merge."""

    doi: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    publication_year: int | None = None
    published_at: datetime | None = None
    journal: str | None = None
    publisher: str | None = None
    openalex_id: str | None = None
    crossref_id: str | None = None
    landing_url: str | None = None
    open_access_status: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, MetadataProvenance] = Field(default_factory=dict)
    conflicts: list[MetadataConflict] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ScholarlyResolution(BaseModel):
    status: ResolutionStatus
    metadata: ScholarlyWorkMetadata | None = None
    providers_resolved: list[MetadataProvenance] = Field(default_factory=list)
    providers_unavailable: list[MetadataProvenance] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
