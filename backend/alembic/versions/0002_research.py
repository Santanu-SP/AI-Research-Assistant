"""Create the research table.

Revision ID: 0002_research
Revises: 0001_backend_foundation
Create Date: 2026-09-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_research"
down_revision: str | None = "0001_backend_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "researching",
                "completed",
                "failed",
                name="research_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "research_depth",
            sa.Enum(
                "quick",
                "standard",
                "deep",
                name="research_depth",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="standard",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_archived_at", "research", ["archived_at"])
    op.create_index("ix_research_domain", "research", ["domain"])
    op.create_index("ix_research_status", "research", ["status"])


def downgrade() -> None:
    op.drop_index("ix_research_status", table_name="research")
    op.drop_index("ix_research_domain", table_name="research")
    op.drop_index("ix_research_archived_at", table_name="research")
    op.drop_table("research")
