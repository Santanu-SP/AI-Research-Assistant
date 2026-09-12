"""Create the documents table.

Revision ID: 0003_documents
Revises: 0002_research
Create Date: 2026-09-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_documents"
down_revision: str | None = "0002_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column(
            "file_type",
            sa.Enum(
                "pdf",
                "docx",
                "txt",
                name="document_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ready",
                "processing",
                "failed",
                name="document_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="ready",
            nullable=False,
        ),
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
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index("ix_documents_file_type", "documents", ["file_type"])
    op.create_index("ix_documents_status", "documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_file_type", table_name="documents")
    op.drop_table("documents")
