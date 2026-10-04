from uuid import UUID

from pydantic import Field

from app.domain.documents import ContentLevel, SourceType
from app.schemas.base import ApiSchema


class RetrievalRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=4000)
    project_id: UUID | None = None


class RetrievalCandidate(ApiSchema):
    chunk_id: UUID
    node_id: str | None = None
    document_id: UUID
    project_id: UUID | None = None
    source_type: SourceType | None = None
    content_level: ContentLevel | None = None
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    page: int | None
    page_end: int | None = None
    section: str | None
    section_path: list[str] | None = None
    text: str
    vector_score: float | None = None
    keyword_score: float | None = None
    hybrid_score: float
    rerank_score: float | None = None


class RetrievalResponse(ApiSchema):
    items: list[RetrievalCandidate]
