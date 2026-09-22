"""Add Google identity, OAuth state, and pgvector chunk embeddings.

Revision ID: 0008_google_auth_and_retrieval
Revises: 0007_authentication
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_google_auth_and_retrieval"
down_revision: str | None = "0007_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
        batch.add_column(sa.Column("google_sub", sa.String(255), nullable=True))
        batch.create_index("ix_users_google_sub", ["google_sub"], unique=True)
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    if is_postgres:
        op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1024)")
        op.execute("CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops)")
    else:
        op.add_column("document_chunks", sa.Column("embedding", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "embedding")
    op.drop_table("oauth_states")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_google_sub")
        batch.drop_column("google_sub")
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
