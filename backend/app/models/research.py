from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Enum, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime
from app.domain.research import ResearchDepth, ResearchProgressStage, ResearchStatus
from app.domain.states import ProjectStatus


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


research_depth_enum = Enum(
    ResearchDepth,
    name="research_depth",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

research_status_enum = Enum(
    ResearchStatus,
    name="research_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

project_status_enum = Enum(
    ProjectStatus,
    name="project_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

research_progress_stage_enum = Enum(
    ResearchProgressStage,
    name="research_progress_stage",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)


class Research(TimestampMixin, Base):
    __tablename__ = "research"
    __table_args__ = (
        CheckConstraint(
            "sources_discovered >= 0",
            name="ck_research_sources_discovered_nonnegative",
        ),
        CheckConstraint(
            "sources_reviewed >= 0",
            name="ck_research_sources_reviewed_nonnegative",
        ),
        CheckConstraint(
            "documents_found >= 0",
            name="ck_research_documents_found_nonnegative",
        ),
        CheckConstraint(
            "sources_reviewed <= sources_discovered",
            name="ck_research_sources_reviewed_lte_discovered",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[ResearchStatus] = mapped_column(
        research_status_enum,
        default=ResearchStatus.DRAFT,
        server_default=ResearchStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    research_depth: Mapped[ResearchDepth] = mapped_column(
        research_depth_enum,
        default=ResearchDepth.STANDARD,
        server_default=ResearchDepth.STANDARD.value,
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
        index=True,
    )
    project_status: Mapped[ProjectStatus | None] = mapped_column(
        project_status_enum,
        default=ProjectStatus.DRAFT,
        nullable=True,
    )
    progress_stage: Mapped[ResearchProgressStage | None] = mapped_column(
        research_progress_stage_enum,
        nullable=True,
    )
    sources_discovered: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    sources_reviewed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    documents_found: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
