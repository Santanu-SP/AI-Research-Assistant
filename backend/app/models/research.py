from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    Uuid,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


# Documents a research run is allowed to read. Only used when the run's
# ``documents_scoped`` flag is set; older runs have no rows here.
research_documents = Table(
    "research_documents",
    Base.metadata,
    Column(
        "research_id",
        Uuid(as_uuid=True),
        ForeignKey("research.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "document_id",
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
    Column("created_at", UTCDateTime(), server_default=func.now(), nullable=False),
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
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    preferred_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(160), nullable=True)
    local_fallback_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Why the model failed on the last attempt: provider, model and a short
    # type (quota, auth, timeout, unavailable, other). Never keys or raw text.
    failure_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allow_shared_providers: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    shared_quota_reserved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    shared_quota_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # True when the run reads only its attached documents (research_documents).
    # False for project runs and for runs made before attachments existed:
    # those use the project's documents, or all of the user's documents.
    documents_scoped: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    # Set when the run should find its own sources online before answering
    # ("all", "scholarly" or "web"). The background job searches, imports and
    # attaches them, so starting the run returns right away.
    discovery_scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attached_documents: Mapped[list["Document"]] = relationship(
        secondary=research_documents,
        lazy="selectin",
        passive_deletes=True,
        order_by="Document.created_at",
    )
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

    @property
    def document_ids(self) -> list[UUID]:
        """IDs of the attached documents (empty for unscoped runs)."""
        return [document.id for document in self.attached_documents]
