"""Add canonical source metadata and structured ingestion nodes.

Revision ID: 0012_canonical_document_metadata
Revises: 0011_project_scope_and_fts
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine


revision: str = "0012_canonical_document_metadata"
down_revision: str | None = "0011_project_scope_and_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


source_type = sa.Enum(
    "uploaded_file",
    "web_page",
    "doi",
    "openalex",
    "crossref",
    name="source_type",
    native_enum=False,
    create_constraint=True,
)
content_level = sa.Enum(
    "full_text",
    "abstract",
    "metadata_only",
    "web_page",
    "user_document",
    name="content_level",
    native_enum=False,
    create_constraint=True,
)


def _json_type() -> TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source_type",
            source_type,
            server_default="uploaded_file",
            nullable=False,
        )
    )
    op.add_column("documents", sa.Column("source_uri", sa.String(length=2048)))
    op.add_column("documents", sa.Column("source_url", sa.String(length=2048)))
    op.add_column("documents", sa.Column("checksum", sa.String(length=64)))
    op.add_column("documents", sa.Column("abstract", sa.Text()))
    op.add_column("documents", sa.Column("openalex_id", sa.String(length=255)))
    op.add_column("documents", sa.Column("crossref_id", sa.String(length=255)))
    op.add_column("documents", sa.Column("publication_year", sa.Integer()))
    op.add_column("documents", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column(
        "documents",
        sa.Column(
            "content_level",
            content_level,
            server_default="user_document",
            nullable=False,
        )
    )
    op.add_column("documents", sa.Column("metadata", _json_type()))
    op.add_column("documents", sa.Column("metadata_provenance", _json_type()))
    op.add_column("documents", sa.Column("parser_name", sa.String(length=100)))
    op.add_column("documents", sa.Column("parser_version", sa.String(length=100)))
    op.add_column("documents", sa.Column("ingestion_version", sa.String(length=100)))
    op.create_index("ix_documents_source_type", "documents", ["source_type"])
    op.create_index("ix_documents_openalex_id", "documents", ["openalex_id"])
    op.create_index("ix_documents_crossref_id", "documents", ["crossref_id"])
    op.create_index("ix_documents_content_level", "documents", ["content_level"])
    op.create_index(
        "ix_documents_ingestion_version",
        "documents",
        ["ingestion_version"],
    )
    op.create_index(
        "ix_documents_user_project_checksum",
        "documents",
        ["user_id", "project_id", "checksum"],
    )

    # All records before this revision came from the upload API. Parsed PDF
    # rows used the retained pypdf pipeline; exact historical package versions
    # were not stored and therefore remain NULL.
    op.execute(
        "UPDATE documents SET parser_name = 'pypdf', "
        "ingestion_version = 'legacy-pdf-v1' WHERE file_type = 'pdf'"
    )

    op.add_column(
        "document_chunks",
        sa.Column("node_id", sa.String(length=64), nullable=True),
    )
    op.add_column("document_chunks", sa.Column("page_end", sa.Integer()))
    op.add_column("document_chunks", sa.Column("section_path", sa.JSON()))
    op.add_column("document_chunks", sa.Column("token_count", sa.Integer()))
    op.add_column("document_chunks", sa.Column("metadata", _json_type()))
    # Existing chunk UUIDs are stable, unique and traceable, so they are the
    # truthful node identity for legacy chunks.
    op.execute(
        "UPDATE document_chunks SET node_id = CAST(id AS VARCHAR(64)) "
        "WHERE node_id IS NULL"
    )

    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_constraint(
            "ck_document_chunks_page_positive",
            type_="check",
        )
        batch.alter_column(
            "page",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch.alter_column(
            "node_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_document_chunks_page_positive",
            "page IS NULL OR page >= 1",
        )
        batch.create_check_constraint(
            "ck_document_chunks_page_end_positive",
            "page_end IS NULL OR page_end >= 1",
        )
        batch.create_check_constraint(
            "ck_document_chunks_page_range",
            "page IS NULL OR page_end IS NULL OR page_end >= page",
        )
        batch.create_check_constraint(
            "ck_document_chunks_token_count_nonnegative",
            "token_count IS NULL OR token_count >= 0",
        )
        batch.create_unique_constraint(
            "uq_document_chunks_node_id",
            ["node_id"],
        )


def downgrade() -> None:
    # Revision 0011 required a page number. Preserve node text during downgrade
    # by using its old compatibility value when a newer unpaged format exists.
    op.execute("UPDATE document_chunks SET page = 1 WHERE page IS NULL")
    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_constraint("uq_document_chunks_node_id", type_="unique")
        batch.drop_constraint(
            "ck_document_chunks_token_count_nonnegative",
            type_="check",
        )
        batch.drop_constraint("ck_document_chunks_page_range", type_="check")
        batch.drop_constraint(
            "ck_document_chunks_page_end_positive",
            type_="check",
        )
        batch.drop_constraint(
            "ck_document_chunks_page_positive",
            type_="check",
        )
        batch.alter_column(
            "page",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_document_chunks_page_positive",
            "page >= 1",
        )
        batch.drop_column("metadata")
        batch.drop_column("token_count")
        batch.drop_column("section_path")
        batch.drop_column("page_end")
        batch.drop_column("node_id")

    op.drop_index("ix_documents_user_project_checksum", table_name="documents")
    op.drop_index("ix_documents_ingestion_version", table_name="documents")
    op.drop_index("ix_documents_content_level", table_name="documents")
    op.drop_index("ix_documents_crossref_id", table_name="documents")
    op.drop_index("ix_documents_openalex_id", table_name="documents")
    op.drop_index("ix_documents_source_type", table_name="documents")
    for column_name in (
        "ingestion_version",
        "parser_version",
        "parser_name",
        "metadata_provenance",
        "metadata",
        "content_level",
        "published_at",
        "publication_year",
        "crossref_id",
        "openalex_id",
        "abstract",
        "checksum",
        "source_url",
        "source_uri",
        "source_type",
    ):
        op.drop_column("documents", column_name)
