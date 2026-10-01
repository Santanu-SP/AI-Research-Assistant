"""Add private research project workspaces.

Revision ID: 0010_research_projects
Revises: 0009_grounded_local_rag
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_research_projects"
down_revision: str | None = "0009_grounded_local_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_projects_user_id",
        "research_projects",
        ["user_id"],
    )
    op.create_index(
        "ix_research_projects_archived_at",
        "research_projects",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_projects_archived_at",
        table_name="research_projects",
    )
    op.drop_index(
        "ix_research_projects_user_id",
        table_name="research_projects",
    )
    op.drop_table("research_projects")
