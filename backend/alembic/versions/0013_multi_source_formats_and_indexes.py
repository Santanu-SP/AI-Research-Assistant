"""Expand source formats and add project metadata filter indexes.

Revision ID: 0013_multi_source_ingestion
Revises: 0012_canonical_document_metadata
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_multi_source_ingestion"
down_revision: str | None = "0012_canonical_document_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_document_type = sa.Enum(
    "pdf", "docx", "txt", name="document_type", native_enum=False, create_constraint=True
)
new_document_type = sa.Enum(
    "pdf",
    "docx",
    "pptx",
    "html",
    "markdown",
    "metadata",
    "txt",
    name="document_type",
    native_enum=False,
    create_constraint=True,
)


def _alter_document_type(from_type: sa.Enum, to_type: sa.Enum) -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        # Recreating the parent table causes SQLite ON DELETE CASCADE to clear
        # chunks. Preserve and restore them explicitly around Alembic's batch.
        op.execute(
            "CREATE TEMPORARY TABLE _document_chunks_0013_backup "
            "AS SELECT * FROM document_chunks"
        )
        with op.batch_alter_table("documents", recreate="always") as batch:
            batch.alter_column(
                "file_type",
                existing_type=from_type,
                type_=to_type,
                existing_nullable=False,
            )
        op.execute(
            "INSERT INTO document_chunks SELECT * FROM _document_chunks_0013_backup"
        )
        op.execute("DROP TABLE _document_chunks_0013_backup")
        return
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "file_type",
            existing_type=from_type,
            type_=to_type,
            existing_nullable=False,
        )


def upgrade() -> None:
    _alter_document_type(old_document_type, new_document_type)
    op.create_index(
        "ix_documents_user_project_source_type",
        "documents",
        ["user_id", "project_id", "source_type"],
    )
    op.create_index(
        "ix_documents_user_project_content_level",
        "documents",
        ["user_id", "project_id", "content_level"],
    )
    op.create_index(
        "ix_documents_user_project_publication_year",
        "documents",
        ["user_id", "project_id", "publication_year"],
    )
    op.create_index(
        "ix_documents_user_project_doi",
        "documents",
        ["user_id", "project_id", "doi"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    newer_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM documents "
            "WHERE file_type IN ('pptx', 'html', 'markdown', 'metadata')"
        )
    )
    if newer_count:
        raise RuntimeError(
            "Cannot downgrade 0013 while multi-source document rows exist"
        )
    op.drop_index("ix_documents_user_project_doi", table_name="documents")
    op.drop_index(
        "ix_documents_user_project_publication_year", table_name="documents"
    )
    op.drop_index("ix_documents_user_project_content_level", table_name="documents")
    op.drop_index("ix_documents_user_project_source_type", table_name="documents")
    _alter_document_type(new_document_type, old_document_type)
