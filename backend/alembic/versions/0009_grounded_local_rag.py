"""Persist grounded local RAG citation metadata.

Revision ID: 0009_grounded_local_rag
Revises: 0008_google_auth_and_retrieval
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_grounded_local_rag"
down_revision: str | None = "0008_google_auth_and_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.alter_column("title", existing_type=sa.String(length=500), nullable=True)
        batch.alter_column(
            "publisher", existing_type=sa.String(length=200), nullable=True
        )
        batch.alter_column("year", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("document_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("chunk_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("page", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("section", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("rerank_score", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("rerank_score")
        batch.drop_column("section")
        batch.drop_column("page")
        batch.drop_column("chunk_id")
        batch.drop_column("document_id")
    # Legacy columns were non-null. Use explicit downgrade-only labels so the
    # schema can be reversed even after PR 3 persisted missing paper metadata.
    op.execute("UPDATE sources SET title = 'Untitled source' WHERE title IS NULL")
    op.execute(
        "UPDATE sources SET publisher = 'Uploaded document' WHERE publisher IS NULL"
    )
    op.execute("UPDATE sources SET year = 1000 WHERE year IS NULL")
    with op.batch_alter_table("sources") as batch:
        batch.alter_column("year", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("title", existing_type=sa.String(length=500), nullable=False)
        batch.alter_column(
            "publisher", existing_type=sa.String(length=200), nullable=False
        )
