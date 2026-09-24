from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiSchema


class RetrievalRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=4000)


class RetrievalCandidate(ApiSchema):
    chunk_id: UUID
    document_id: UUID
    paper_title: str | None
    authors: list[str] | None
    doi: str | None
    page: int
    section: str | None
    text: str
    vector_score: float | None = None
    keyword_score: float | None = None
    hybrid_score: float
    rerank_score: float | None = None


class RetrievalResponse(ApiSchema):
    items: list[RetrievalCandidate]
