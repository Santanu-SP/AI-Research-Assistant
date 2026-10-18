from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_values, make_str_enum
from app.db.types import UTCDateTime
from app.domain.research import ResearchDepth, ResearchProgressStage, ResearchStatus
from app.domain.states import ProjectStatus

_enum_values = enum_values

research_depth_enum = make_str_enum(ResearchDepth, name="research_depth")
research_status_enum = make_str_enum(ResearchStatus, name="research_status")
project_status_enum = make_str_enum(ProjectStatus, name="project_status")
research_progress_stage_enum = make_str_enum(
    ResearchProgressStage, name="research_progress_stage"
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
        Index("ix_research_user_project", "user_id", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    project: Mapped["ResearchProject | None"] = relationship(
        back_populates="research_runs"
    )
    report: Mapped["ResearchReport | None"] = relationship(
        back_populates="research",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="research",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )