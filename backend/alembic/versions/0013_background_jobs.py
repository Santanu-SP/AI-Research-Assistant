"""Add the background job queue, email verification, and owner cascades.

Revision ID: 0013_background_jobs
Revises: 0012_canonical_document_metadata
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_background_jobs"
down_revision: str | None = "0012_canonical_document_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_owner_fk(table: str, constraint: str, ondelete: str) -> None:
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(constraint, type_="foreignkey")
        batch.create_foreign_key(constraint, "users", ["user_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_background_jobs_state_run_after", "background_jobs", ["state", "run_after"])
    op.create_index("ix_background_jobs_target", "background_jobs", ["kind", "target_id"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Accounts that already signed in with Google have a provider-verified email.
    op.execute("UPDATE users SET email_verified_at = updated_at WHERE google_sub IS NOT NULL")

    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])

    # Deleting an account removes the documents and research it owns instead
    # of leaving ownerless rows behind.
    _replace_owner_fk("documents", "fk_documents_user_id_users", "CASCADE")
    _replace_owner_fk("research", "fk_research_user_id_users", "CASCADE")


def downgrade() -> None:
    _replace_owner_fk("research", "fk_research_user_id_users", "SET NULL")
    _replace_owner_fk("documents", "fk_documents_user_id_users", "SET NULL")
    op.drop_index("ix_oauth_states_expires_at", table_name="oauth_states")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
    op.drop_index("ix_background_jobs_target", table_name="background_jobs")
    op.drop_index("ix_background_jobs_state_run_after", table_name="background_jobs")
    op.drop_table("background_jobs")
