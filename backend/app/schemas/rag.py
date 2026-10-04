from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.domain.documents import ContentLevel, SourceType
from app.domain.research import ResearchDepth
from app.schemas.base import ApiSchema


class ResearchQueryRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=10_000)
    project_id: UUID | None = None
    research_depth: ResearchDepth = ResearchDepth.STANDARD


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
