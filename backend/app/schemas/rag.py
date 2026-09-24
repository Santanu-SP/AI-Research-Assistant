from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.domain.research import ResearchDepth
from app.schemas.base import ApiSchema


class ResearchQueryRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=10_000)
    research_depth: ResearchDepth = ResearchDepth.STANDARD


class EvidenceItem(ApiSchema):
    source_id: str
    document_id: UUID
    chunk_id: UUID
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    page: int
    section: str | None
    text: str
    rerank_score: float


class ValidatedCitation(ApiSchema):
    citation_id: str
    document_id: UUID
    chunk_id: UUID
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    page: int
    section: str | None
    excerpt: str


class ResearchQueryResponse(ApiSchema):
    research_id: UUID
    answer: str
    citations: list[ValidatedCitation]
    hybrid_candidate_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    insufficient_evidence: bool = False
