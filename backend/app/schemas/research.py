from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from app.domain.research import (
    ResearchDepth,
    ResearchProgressStage,
    ResearchProgressStepStatus,
    ResearchStatus,
)
from app.schemas.base import ApiSchema

QuestionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]
TitleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
DomainText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]


class ResearchCreate(ApiSchema):
    question: QuestionText
    title: TitleText | None = None
    domain: DomainText | None = None
    research_depth: ResearchDepth = ResearchDepth.STANDARD


class ResearchUpdate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    title: TitleText | None = None
    question: QuestionText | None = None
    domain: DomainText | None = None
    research_depth: ResearchDepth | None = None

    @model_validator(mode="after")
    def validate_partial_update(self) -> ResearchUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        non_nullable_fields = {"title", "question", "research_depth"}
        null_fields = [
            field
            for field in non_nullable_fields & self.model_fields_set
            if getattr(self, field) is None
        ]
        if null_fields:
            raise ValueError(f"Fields cannot be null: {', '.join(sorted(null_fields))}")
        return self


class ResearchResponse(ApiSchema):
    id: UUID
    title: str
    question: str
    domain: str | None
    status: ResearchStatus
    research_depth: ResearchDepth
    source_count: int = 0
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ResearchListResponse(ApiSchema):
    items: list[ResearchResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ResearchProgressStep(ApiSchema):
    id: ResearchProgressStage
    title: str
    status: ResearchProgressStepStatus


class ResearchProgressResponse(ApiSchema):
    id: UUID
    question: str
    status: ResearchStatus
    research_depth: ResearchDepth
    current_stage: ResearchProgressStage | None
    current_step_index: int | None = Field(default=None, ge=0, le=4)
    total_steps: int = Field(default=5, ge=5, le=5)
    steps: list[ResearchProgressStep]
    sources_discovered: int = Field(ge=0)
    sources_reviewed: int = Field(ge=0)
    documents_found: int = Field(ge=0)
    started_at: datetime | None
    stage_started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
