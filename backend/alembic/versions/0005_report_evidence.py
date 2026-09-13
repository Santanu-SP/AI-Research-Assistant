"""Add report, section, source, and citation tables.

Revision ID: 0005_report_evidence
Revises: 0004_research_progress
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_report_evidence"
down_revision: str | None = "0004_research_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("dossier_ref", sa.String(length=100), nullable=False),
        sa.Column("reading_time_minutes", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reading_time_minutes >= 1",
            name="ck_research_reports_reading_time_positive",
        ),
        sa.CheckConstraint("version >= 1", name="ck_research_reports_version_positive"),
        sa.ForeignKeyConstraint(["research_id"], ["research.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=200), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column(
            "source_type",
            sa.Enum(
                "peer-reviewed",
                "official-documentation",
                "institutional",
                "technical-report",
                "preprint",
                name="source_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("relevant_excerpt", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("bibtex", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("number >= 1", name="ck_sources_number_positive"),
        sa.CheckConstraint("year >= 1000", name="ck_sources_year_minimum"),
        sa.ForeignKeyConstraint(["research_id"], ["research.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_id", "number", name="uq_sources_research_number"),
    )
    op.create_index("ix_sources_research_id", "sources", ["research_id"])

    op.create_table(
        "report_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("heading", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0", name="ck_report_sections_position_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["research_reports.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id", "position", name="uq_report_sections_report_position"
        ),
    )
    op.create_index("ix_report_sections_report_id", "report_sections", ["report_id"])

    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("position >= 0", name="ck_citations_position_nonnegative"),
        sa.ForeignKeyConstraint(
            ["section_id"], ["report_sections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "section_id", "position", name="uq_citations_section_position"
        ),
        sa.UniqueConstraint(
            "section_id", "source_id", name="uq_citations_section_source"
        ),
    )
    op.create_index("ix_citations_section_id", "citations", ["section_id"])
    op.create_index("ix_citations_source_id", "citations", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_citations_source_id", table_name="citations")
    op.drop_index("ix_citations_section_id", table_name="citations")
    op.drop_table("citations")
    op.drop_index("ix_report_sections_report_id", table_name="report_sections")
    op.drop_table("report_sections")
    op.drop_index("ix_sources_research_id", table_name="sources")
    op.drop_table("sources")
    op.drop_table("research_reports")
