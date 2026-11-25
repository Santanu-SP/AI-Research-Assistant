from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from app.domain.collaboration import CollaboratorRole
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
    project_id: UUID | None = None
    # See ResearchQueryRequest.document_ids.
    document_ids: list[UUID] | None = Field(default=None, max_length=100)
    title: TitleText | None = None
    domain: DomainText | None = None
    research_depth: ResearchDepth = ResearchDepth.STANDARD


class ResearchUpdate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    title: TitleText | None = None
    question: QuestionText | None = None
    domain: DomainText | None = None
    research_depth: ResearchDepth | None = None
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_partial_update(self) -> ResearchUpdate:
        if not (self.model_fields_set - {"version"}):
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
    project_id: UUID | None = None
    title: str
    question: str
    domain: str | None
    status: ResearchStatus
    research_depth: ResearchDepth
    version: int = Field(default=1, ge=1)
    my_role: CollaboratorRole = CollaboratorRole.OWNER
    is_shared: bool = False
    member_count: int = Field(default=1, ge=1)
    owner_name: str | None = None
    source_count: int = 0
    # True when the run reads only ``document_ids``; false for project runs
    # and older runs, which use the project's or all of the user's documents.
    documents_scoped: bool = False
    document_ids: list[UUID] = Field(default_factory=list)
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
    project_id: UUID | None = None
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
    # Only set for failed runs: a short, safe reason the UI can explain.
    failure_reason: Literal[
        "paused",
        "model_unavailable",
        "quota_reached",
        "no_ready_documents",
        "no_discoverable_sources",
        "discovery_disabled",
        "unexpected",
    ] | None = None
    # For model failures: which provider and model failed and how
    # (quota, auth, timeout, unavailable, other). Never keys or raw messages.
    failure_provider: str | None = None
    failure_model: str | None = None
    failure_type: Literal["quota", "auth", "timeout", "unavailable", "other"] | None = None
    # Documents in this run's scope (its project, or all of the user's).
    documents_ready: int = Field(default=0, ge=0)
    documents_preparing: int = Field(default=0, ge=0)
    # True when the run finds its own sources online before answering.
    auto_discover: bool = False
