from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.documents import ContentLevel, SourceType
from app.schemas.base import ApiSchema
from app.schemas.documents import DocumentResponse

DiscoveryScope = Literal["all", "scholarly", "web"]
DiscoveryProviderName = Literal["openalex", "crossref", "arxiv", "wikipedia", "news"]
DiscoveryTrustTier = Literal[
    "peer-reviewed",
    "preprint",
    "institutional",
    "official-documentation",
    "news",
]


class DiscoveredSourceCandidate(ApiSchema):
    candidate_id: str = Field(min_length=1, max_length=255)
    provider: DiscoveryProviderName
    trust_tier: DiscoveryTrustTier
    source_type: SourceType
    content_level: ContentLevel
    title: str = Field(min_length=1, max_length=1000)
    authors: list[str] = Field(default_factory=list, max_length=50)
    publication_year: int | None = Field(default=None, ge=1000, le=9999)
    publisher: str | None = Field(default=None, max_length=300)
    abstract: str | None = Field(default=None, max_length=20_000)
    doi: str | None = Field(default=None, max_length=255)
    openalex_id: str | None = Field(default=None, max_length=255)
    crossref_id: str | None = Field(default=None, max_length=255)
    url: str = Field(min_length=8, max_length=2048)
    open_access_pdf_url: str | None = Field(default=None, max_length=2048)
    citation_count: int | None = Field(default=None, ge=0)
    is_open_access: bool = False
    already_in_library: bool = False
    existing_document_id: UUID | None = None


class DiscoverySearchRequest(ApiSchema):
    query: str = Field(min_length=2, max_length=500)
    scope: DiscoveryScope = "all"
    limit: int = Field(default=8, ge=1, le=20)
    project_id: UUID | None = None


class DiscoverySearchResponse(ApiSchema):
    query: str
    scope: DiscoveryScope
    items: list[DiscoveredSourceCandidate]
    provider_errors: list[str] = Field(default_factory=list)


class DiscoveryImportRequest(ApiSchema):
    project_id: UUID | None = None
    items: list[DiscoveredSourceCandidate] = Field(min_length=1, max_length=8)
    fetch_full_text: bool = True


class DiscoveryImportFailure(ApiSchema):
    title: str
    url: str
    reason: str


class DiscoveryImportResponse(ApiSchema):
    documents: list[DocumentResponse]
    reused_count: int = Field(default=0, ge=0)
    imported_count: int = Field(default=0, ge=0)
    failed: list[DiscoveryImportFailure] = Field(default_factory=list)


class DiscoveryStatusResponse(ApiSchema):
    enabled: bool
    scopes: list[DiscoveryScope]
    providers: list[DiscoveryProviderName]
    auto_import_limit: int = Field(ge=1)
