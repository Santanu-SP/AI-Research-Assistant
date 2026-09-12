"""Add persisted research progress state.

Revision ID: 0004_research_progress
Revises: 0003_documents
Create Date: 2026-09-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_research_progress"
down_revision: str | None = "0003_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.add_column(
            sa.Column(
                "project_status",
                sa.Enum(
                    "DRAFT",
                    "PAPERS_DISCOVERED",
                    "PAPERS_SELECTED",
                    "PROCESSING",
                    "RESEARCH_READY",
                    "ANALYZING",
                    "REVIEW_READY",
                    "REPORT_READY",
                    "PROCESSING_FAILED",
                    name="project_status",
                    native_enum=False,
                    create_constraint=True,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "progress_stage",
                sa.Enum(
                    "planning",
                    "searching_sources",
                    "finding_documents",
                    "reviewing_evidence",
                    "building_synthesis",
                    name="research_progress_stage",
                    native_enum=False,
                    create_constraint=True,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "sources_discovered",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "sources_reviewed",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "documents_found",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stage_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_research_sources_discovered_nonnegative",
            "sources_discovered >= 0",
        )
        batch_op.create_check_constraint(
            "ck_research_sources_reviewed_nonnegative",
            "sources_reviewed >= 0",
        )
        batch_op.create_check_constraint(
            "ck_research_documents_found_nonnegative",
            "documents_found >= 0",
        )
        batch_op.create_check_constraint(
            "ck_research_sources_reviewed_lte_discovered",
            "sources_reviewed <= sources_discovered",
        )


def downgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.drop_constraint(
            "ck_research_sources_reviewed_lte_discovered",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_research_documents_found_nonnegative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_research_sources_reviewed_nonnegative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_research_sources_discovered_nonnegative",
            type_="check",
        )
        batch_op.drop_constraint("research_progress_stage", type_="check")
        batch_op.drop_constraint("project_status", type_="check")
        batch_op.drop_column("failed_at")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("stage_started_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("documents_found")
        batch_op.drop_column("sources_reviewed")
        batch_op.drop_column("sources_discovered")
        batch_op.drop_column("progress_stage")
        batch_op.drop_column("project_status")
