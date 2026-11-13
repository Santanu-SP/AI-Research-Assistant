"""Add Neon pgvector check, storage/embedding columns, BYOK keys, and telemetry.

Revision ID: 0014_neon_multimodal_router_byok
Revises: 0013_background_jobs
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014_neon_multimodal_router_byok"
down_revision: str | None = "0013_background_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    with op.batch_alter_table("documents") as batch:
        batch.add_column(
            sa.Column(
                "storage_backend",
                sa.String(length=32),
                server_default="local",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("embedding_model", sa.String(length=160), nullable=True)
        )
        batch.add_column(
            sa.Column("embedding_version", sa.String(length=100), nullable=True)
        )

    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_user_api_keys_user_provider"
        ),
    )
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])
    op.create_index(
        "ix_user_api_keys_user_active",
        "user_api_keys",
        ["user_id", "is_active"],
    )

    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("details", _json_type(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_telemetry_events_user_id", "telemetry_events", ["user_id"])
    op.create_index("ix_telemetry_events_category", "telemetry_events", ["category"])
    op.create_index("ix_telemetry_events_provider", "telemetry_events", ["provider"])
    op.create_index(
        "ix_telemetry_events_category_created",
        "telemetry_events",
        ["category", "created_at"],
    )
    op.create_index(
        "ix_telemetry_events_user_created",
        "telemetry_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_events_user_created", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_category_created", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_provider", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_category", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_user_id", table_name="telemetry_events")
    op.drop_table("telemetry_events")

    op.drop_index("ix_user_api_keys_user_active", table_name="user_api_keys")
    op.drop_index("ix_user_api_keys_user_id", table_name="user_api_keys")
    op.drop_table("user_api_keys")

    with op.batch_alter_table("documents") as batch:
        batch.drop_column("embedding_version")
        batch.drop_column("embedding_model")
        batch.drop_column("storage_backend")

