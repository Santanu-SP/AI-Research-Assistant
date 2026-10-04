"""Scope documents and research runs to projects and add indexed FTS.

Revision ID: 0011_project_scope_and_fts
Revises: 0010_research_projects
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_project_scope_and_fts"
down_revision: str | None = "0010_research_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_documents_project_id_research_projects",
            "research_projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_documents_project_id", ["project_id"])
        batch.create_index(
            "ix_documents_user_project",
            ["user_id", "project_id"],
        )

    with op.batch_alter_table("research") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_research_project_id_research_projects",
            "research_projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_research_project_id", ["project_id"])
        batch.create_index(
            "ix_research_user_project",
            ["user_id", "project_id"],
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "document_chunks",
            sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        )
        op.execute(
            "UPDATE document_chunks "
            "SET search_vector = to_tsvector('english', coalesce(text, ''))"
        )
        op.execute(
            """
            CREATE FUNCTION document_chunks_search_vector_update()
            RETURNS trigger AS $$
            BEGIN
                NEW.search_vector := to_tsvector('english', coalesce(NEW.text, ''));
                RETURN NEW;
            END
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_document_chunks_search_vector
            BEFORE INSERT OR UPDATE OF text ON document_chunks
            FOR EACH ROW EXECUTE FUNCTION document_chunks_search_vector_update()
            """
        )
        op.create_index(
            "ix_document_chunks_search_vector_gin",
            "document_chunks",
            ["search_vector"],
            postgresql_using="gin",
        )
    else:
        op.add_column(
            "document_chunks",
            sa.Column("search_vector", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_document_chunks_search_vector_gin",
            table_name="document_chunks",
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_document_chunks_search_vector "
            "ON document_chunks"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS document_chunks_search_vector_update()"
        )
    op.drop_column("document_chunks", "search_vector")

    with op.batch_alter_table("research") as batch:
        batch.drop_index("ix_research_user_project")
        batch.drop_index("ix_research_project_id")
        batch.drop_constraint(
            "fk_research_project_id_research_projects",
            type_="foreignkey",
        )
        batch.drop_column("project_id")

    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_user_project")
        batch.drop_index("ix_documents_project_id")
        batch.drop_constraint(
            "fk_documents_project_id_research_projects",
            type_="foreignkey",
        )
        batch.drop_column("project_id")
