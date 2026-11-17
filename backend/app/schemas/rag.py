from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.documents import ContentLevel, SourceType
from app.domain.research import ResearchDepth
from app.providers.base import validate_model_name
from app.schemas.base import ApiSchema


class ResearchQueryRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=10_000)
    project_id: UUID | None = None
    # The documents this research may read. Outside a project the list must
    # not be empty unless auto_discover is explicitly opted in. Left out
    # entirely, the run uses the project's documents (or older client behaviour).
    document_ids: list[UUID] | None = Field(default=None, max_length=100)
    auto_discover: bool = False
    discovery_scope: Literal["all", "scholarly", "web"] = "all"
    research_depth: ResearchDepth = ResearchDepth.STANDARD
    preferred_provider: str | None = Field(default=None, max_length=64)
    model_override: str | None = Field(default=None, max_length=160)
    local_fallback_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_model_options(self) -> "ResearchQueryRequest":
        if self.preferred_provider is not None:
            cleaned_provider = self.preferred_provider.strip().lower()
            self.preferred_provider = cleaned_provider or None
        if self.model_override is not None:
            cleaned_override = self.model_override.strip()
            self.model_override = (
                validate_model_name(cleaned_override, provider=self.preferred_provider)
                if cleaned_override
                else None
            )
        return self


class ReportFollowupRequest(ApiSchema):
    """Lightweight follow-up question scoped to a completed research report."""

    question: str = Field(min_length=1, max_length=2000)
    preferred_provider: str | None = Field(default=None, max_length=64)
    model_override: str | None = Field(default=None, max_length=160)
    local_fallback_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_model_options(self) -> "ReportFollowupRequest":
        if self.preferred_provider is not None:
            cleaned_provider = self.preferred_provider.strip().lower()
            self.preferred_provider = cleaned_provider or None
        if self.model_override is not None:
            cleaned_override = self.model_override.strip()
            self.model_override = (
                validate_model_name(cleaned_override, provider=self.preferred_provider)
                if cleaned_override
                else None
            )
        return self


class ResearchRetryRequest(ApiSchema):
    """Run a failed research item again, optionally with an edited question.

    Every field is optional; anything left out keeps the value from the
    previous attempt.
    """

    query: str | None = Field(default=None, min_length=1, max_length=10_000)
    research_depth: ResearchDepth | None = None
    preferred_provider: str | None = Field(default=None, max_length=64)
    model_override: str | None = Field(default=None, max_length=160)
    local_fallback_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_model_options(self) -> "ResearchRetryRequest":
        if self.preferred_provider is not None:
            cleaned_provider = self.preferred_provider.strip().lower()
            self.preferred_provider = cleaned_provider or None
        if self.model_override is not None:
            cleaned_override = self.model_override.strip()
            self.model_override = (
                validate_model_name(cleaned_override, provider=self.preferred_provider)
                if cleaned_override
                else None
            )
        return self


class ReportFollowupRequest(ApiSchema):
    """Lightweight follow-up question scoped to a completed research report."""

    question: str = Field(min_length=1, max_length=2000)
    preferred_provider: str | None = Field(default=None, max_length=64)
    model_override: str | None = Field(default=None, max_length=160)
    local_fallback_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_model_options(self) -> "ReportFollowupRequest":
        if self.preferred_provider is not None:
            cleaned_provider = self.preferred_provider.strip().lower()
            self.preferred_provider = cleaned_provider or None
        if self.model_override is not None:
            cleaned_override = self.model_override.strip()
            self.model_override = (
                validate_model_name(cleaned_override, provider=self.preferred_provider)
                if cleaned_override
                else None
            )
        return self


class EvidenceItem(ApiSchema):
    source_id: str
    node_id: str | None = None
    document_id: UUID
    project_id: UUID | None = None
    source_type: SourceType | None = None
    content_level: ContentLevel | None = None
    chunk_id: UUID
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    url: str | None = None
    publisher: str | None = None
    year: int | None = None
    page: int | None
    page_end: int | None = None
    section: str | None
    section_path: list[str] | None = None
    text: str
    rerank_score: float


class ValidatedCitation(ApiSchema):
    citation_id: str
    node_id: str | None = None
    document_id: UUID
    project_id: UUID | None = None
    source_type: SourceType | None = None
    content_level: ContentLevel | None = None
    chunk_id: UUID
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    url: str | None = None
    publisher: str | None = None
    year: int | None = None
    page: int | None
    page_end: int | None = None
    section: str | None
    section_path: list[str] | None = None
    excerpt: str


class ResearchQueryResponse(ApiSchema):
    research_id: UUID
    project_id: UUID | None = None
    answer: str
    citations: list[ValidatedCitation]
    hybrid_candidate_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    insufficient_evidence: bool = False
