from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.reports import SourceType

if TYPE_CHECKING:
    from app.models.research import Research


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


source_type_enum = Enum(
    SourceType,
    name="source_type",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)


class ResearchReport(TimestampMixin, Base):
    """The current grounded report associated with one research record."""

    __tablename__ = "research_reports"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_research_reports_version_positive"),
        CheckConstraint(
            "reading_time_minutes >= 1",
            name="ck_research_reports_reading_time_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    dossier_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    reading_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )

    research: Mapped[Research] = relationship(back_populates="report")
    sections: Mapped[list[ReportSection]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReportSection.position",
    )


class ReportSection(TimestampMixin, Base):
    __tablename__ = "report_sections"
    __table_args__ = (
        CheckConstraint(
            "position >= 0", name="ck_report_sections_position_nonnegative"
        ),
        UniqueConstraint(
            "report_id", "position", name="uq_report_sections_report_position"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    heading: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    report: Mapped[ResearchReport] = relationship(back_populates="sections")
    citations: Mapped[list[Citation]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Citation.position",
    )


class Source(TimestampMixin, Base):
    """Research-scoped evidence that can be cited by the current report."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("number >= 1", name="ck_sources_number_positive"),
        CheckConstraint("year >= 1000", name="ck_sources_year_minimum"),
        UniqueConstraint("research_id", "number", name="uq_sources_research_number"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(source_type_enum, nullable=False)
    relevant_excerpt: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(255))
    bibtex: Mapped[str | None] = mapped_column(Text)

    research: Mapped[Research] = relationship(back_populates="sources")
    citations: Mapped[list[Citation]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Citation(TimestampMixin, Base):
    """An ordered link from one report section to one evidence source."""

    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_citations_position_nonnegative"),
        UniqueConstraint(
            "section_id", "position", name="uq_citations_section_position"
        ),
        UniqueConstraint("section_id", "source_id", name="uq_citations_section_source"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    section: Mapped[ReportSection] = relationship(back_populates="citations")
    source: Mapped[Source] = relationship(back_populates="citations")
