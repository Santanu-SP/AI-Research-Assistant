from uuid import UUID

from pydantic import Field, model_validator

from app.domain.documents import ContentLevel, SourceType
from app.schemas.base import ApiSchema


class RetrievalFilters(ApiSchema):
    document_ids: list[UUID] = Field(default_factory=list, max_length=100)
    source_types: list[SourceType] = Field(default_factory=list, max_length=20)
    content_levels: list[ContentLevel] = Field(default_factory=list, max_length=20)
    year_from: int | None = Field(default=None, ge=1000, le=3000)
    year_to: int | None = Field(default=None, ge=1000, le=3000)
    doi: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_years(self) -> "RetrievalFilters":
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("yearFrom cannot be later than yearTo")
        return self


class RetrievalRequest(ApiSchema):
    query: str = Field(min_length=1, max_length=4000)
    project_id: UUID | None = None
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


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
