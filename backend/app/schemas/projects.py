from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from app.schemas.base import ApiSchema

ProjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ProjectDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5_000),
]


class ResearchProjectCreate(ApiSchema):
    name: ProjectName
    description: ProjectDescription | None = None


class ResearchProjectUpdate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    description: ProjectDescription | None = None

    @model_validator(mode="after")
    def validate_partial_update(self) -> "ResearchProjectUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Project name cannot be null")
        return self


class ResearchProjectResponse(ApiSchema):
    id: UUID
    name: str
    description: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchProjectListResponse(ApiSchema):
    items: list[ResearchProjectResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
