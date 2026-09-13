from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, StringConstraints

from app.domain.reports import SourceType
from app.domain.research import ResearchStatus
from app.schemas.base import ApiSchema

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
LongTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
BodyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200_000)
]
OptionalText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200_000)
]


class CitationCreate(ApiSchema):
    """Internal pipeline input linking a section to a supplied source ID."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_id: UUID
    position: int = Field(ge=0)


class ReportSectionCreate(ApiSchema):
    """Internal pipeline input; this is intentionally not a public endpoint."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    heading: ShortText
    content: BodyText
    quote: OptionalText | None = None
    position: int = Field(ge=0)
    citations: list[CitationCreate] = Field(default_factory=list)


class SourceCreate(ApiSchema):
    """Internal evidence input with a caller-assigned stable display number."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    number: int = Field(ge=1)
    title: LongTitle
    publisher: ShortText
    authors: list[ShortText] = Field(min_length=1, max_length=100)
    year: int = Field(ge=1000, le=9999)
    url: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)] | None
    ) = None
    source_type: SourceType
    relevant_excerpt: OptionalText | None = None
    doi: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
        ]
        | None
    ) = None
    bibtex: OptionalText | None = None


class ResearchReportCreate(ApiSchema):
    """Atomic internal input for a report and its complete evidence graph."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    title: ShortText
    summary: BodyText
    dossier_ref: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    reading_time_minutes: int = Field(ge=1)
    version: int = Field(default=1, ge=1)
    sections: list[ReportSectionCreate] = Field(default_factory=list)
    sources: list[SourceCreate] = Field(default_factory=list)


class CitationResponse(ApiSchema):
    id: UUID
    source_id: UUID
    number: int = Field(ge=1)
    position: int = Field(ge=0)


class ReportSectionResponse(ApiSchema):
    id: UUID
    heading: str
    content: str
    quote: str | None
    position: int = Field(ge=0)
    citation_ids: list[int]
    citations: list[CitationResponse]
    created_at: datetime
    updated_at: datetime


class SourceResponse(ApiSchema):
    id: UUID
    number: int = Field(ge=1)
    title: str
    publisher: str
    authors: list[str]
    year: int
    url: str | None
    source_type: SourceType
    relevant_excerpt: str | None
    citation_count: int = Field(ge=0)
    doi: str | None
    bibtex: str | None
    created_at: datetime
    updated_at: datetime


class ResearchReportResponse(ApiSchema):
    id: UUID
    research_id: UUID
    title: str
    summary: str
    dossier_ref: str
    reading_time_minutes: int = Field(ge=1)
    source_count: int = Field(ge=0)
    status: ResearchStatus
    version: int = Field(ge=1)
    sections: list[ReportSectionResponse]
    created_at: datetime
    updated_at: datetime


class ComposedReportResponse(ApiSchema):
    report: ResearchReportResponse
    sources: list[SourceResponse]
