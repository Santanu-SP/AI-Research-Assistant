"""Let a research run use only the documents attached to it.

Adds ``research_documents`` (which documents a run may read) and
``research.documents_scoped``. Existing runs keep ``documents_scoped`` false,
so they go on using their project's documents, or all of the user's
documents, exactly as before.

Revision ID: 0017_research_documents
Revises: 0016_model_prefs_usage_quota
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0017_research_documents"
down_revision: str | None = "0016_model_prefs_usage_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.add_column(
            sa.Column(
                "documents_scoped",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    op.create_table(
        "research_documents",
        sa.Column(
            "research_id",
            sa.Uuid(),
            sa.ForeignKey("research.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_research_documents_document_id", "research_documents", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_documents_document_id", table_name="research_documents")
    op.drop_table("research_documents")
    with op.batch_alter_table("research") as batch_op:
        batch_op.drop_column("documents_scoped")
