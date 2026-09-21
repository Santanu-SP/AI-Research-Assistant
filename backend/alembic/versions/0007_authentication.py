"""Add users, revocable sessions, and optional ownership for existing records.

Revision ID: 0007_authentication
Revises: 0006_document_ingestion
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_authentication"
down_revision: str | None = "0006_document_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("user_id", sa.Uuid()))
        batch.create_foreign_key("fk_documents_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_documents_user_id", ["user_id"])
    with op.batch_alter_table("research") as batch:
        batch.add_column(sa.Column("user_id", sa.Uuid()))
        batch.create_foreign_key("fk_research_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_research_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("research") as batch:
        batch.drop_index("ix_research_user_id")
        batch.drop_constraint("fk_research_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_user_id")
        batch.drop_constraint("fk_documents_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
