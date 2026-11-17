"""Persist lightweight grounded follow-up Q&A turns on composed research reports.

Revision ID: 0021_report_followups
Revises: 0020_research_discovery_scope
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0021_report_followups"
down_revision: str | None = "0020_research_discovery_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_followups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citation_numbers", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column(
            "insufficient_evidence",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_report_followups_position_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["research_reports.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id",
            "position",
            name="uq_report_followups_report_position",
        ),
    )
    op.create_index(
        op.f("ix_report_followups_report_id"),
        "report_followups",
        ["report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_report_followups_report_id"), table_name="report_followups")
    op.drop_table("report_followups")
