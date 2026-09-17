"""Add PDF ingestion metadata and page-aware document chunks.

Revision ID: 0006_document_ingestion
Revises: 0005_report_evidence
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_document_ingestion"
down_revision: str | None = "0005_report_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_status = sa.Enum(
    "ready",
    "processing",
    "failed",
    name="document_status",
    native_enum=False,
    create_constraint=True,
)
new_status = sa.Enum(
    "uploaded",
    "processing",
    "indexed",
    "failed",
    name="document_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    # "ready" was the old name for a stored file. The old pipeline never left
    # records in "processing", so it is a safe bridge value while SQLite
    # recreates the enum-backed CHECK constraint.
    op.execute("UPDATE documents SET status = 'processing' WHERE status = 'ready'")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=old_status,
            type_=new_status,
            existing_nullable=False,
            server_default="uploaded",
        )
        batch_op.add_column(sa.Column("title", sa.String(length=1000)))
        batch_op.add_column(sa.Column("authors", sa.JSON()))
        batch_op.add_column(sa.Column("doi", sa.String(length=255)))
        batch_op.add_column(sa.Column("page_count", sa.Integer()))
        batch_op.add_column(
            sa.Column(
                "uploaded_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("processing_error", sa.Text()))
        batch_op.create_index("ix_documents_doi", ["doi"])
    # Legacy "ready" rows were stored but never extracted, so they remain
    # truthful as uploaded documents awaiting processing.
    op.execute("UPDATE documents SET status = 'uploaded' WHERE status = 'processing'")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=500)),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("page >= 1", name="ck_document_chunks_page_positive"),
        sa.CheckConstraint(
            "chunk_index >= 0", name="ck_document_chunks_index_nonnegative"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id", "document_chunks", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.execute(
        "UPDATE documents SET status = 'processing' "
        "WHERE status IN ('uploaded', 'indexed')"
    )
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_doi")
        batch_op.drop_column("processing_error")
        batch_op.drop_column("uploaded_at")
        batch_op.drop_column("page_count")
        batch_op.drop_column("doi")
        batch_op.drop_column("authors")
        batch_op.drop_column("title")
        batch_op.alter_column(
            "status",
            existing_type=new_status,
            type_=old_status,
            existing_nullable=False,
            server_default="ready",
        )
    op.execute("UPDATE documents SET status = 'ready' WHERE status = 'processing'")
