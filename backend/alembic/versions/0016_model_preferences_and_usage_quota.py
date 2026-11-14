"""Persist model/local preferences, research runtime options, and atomic usage/quota tables.

Revision ID: 0016_model_preferences_and_usage_quota
Revises: 0015_multimodal_document_enums
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016_model_preferences_and_usage_quota"
down_revision: str | None = "0015_multimodal_document_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("local_fallback_enabled", sa.Boolean(), nullable=True),
        )

    with op.batch_alter_table("research") as batch_op:
        batch_op.add_column(sa.Column("preferred_provider", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("model_override", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("local_fallback_enabled", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("allow_shared_providers", sa.Boolean(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column("shared_quota_reserved", sa.Boolean(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("shared_quota_date", sa.Date(), nullable=True))

    op.create_table(
        "user_model_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(160), nullable=False),
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
        sa.UniqueConstraint("user_id", "provider", name="uq_user_model_prefs_user_provider"),
    )
    op.create_index("ix_user_model_preferences_user_id", "user_model_preferences", ["user_id"])

    op.create_table(
        "daily_quota_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("shared_requests_used", sa.Integer(), server_default="0", nullable=False),
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
        sa.UniqueConstraint("usage_date", "scope_key", name="uq_daily_quota_usage_date_scope"),
        sa.CheckConstraint("shared_requests_used >= 0", name="ck_daily_quota_usage_nonnegative"),
    )

    op.create_table(
        "model_usage_daily",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(160), nullable=False),
        sa.Column("usage_source", sa.String(16), server_default="shared", nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
            "usage_date",
            "user_id",
            "provider",
            "model_name",
            "usage_source",
            name="uq_model_usage_daily_bucket",
        ),
        sa.CheckConstraint(
            "request_count >= 0",
            name="ck_model_usage_daily_request_count_nonnegative",
        ),
    )
    op.create_index("ix_model_usage_daily_usage_date", "model_usage_daily", ["usage_date"])
    op.create_index("ix_model_usage_daily_user_id", "model_usage_daily", ["user_id"])
    op.create_index(
        "ix_model_usage_daily_user_date",
        "model_usage_daily",
        ["user_id", "usage_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_usage_daily_user_date", table_name="model_usage_daily")
    op.drop_index("ix_model_usage_daily_user_id", table_name="model_usage_daily")
    op.drop_index("ix_model_usage_daily_usage_date", table_name="model_usage_daily")
    op.drop_table("model_usage_daily")
    op.drop_table("daily_quota_usage")
    op.drop_index("ix_user_model_preferences_user_id", table_name="user_model_preferences")
    op.drop_table("user_model_preferences")

    with op.batch_alter_table("research") as batch_op:
        batch_op.drop_column("shared_quota_date")
        batch_op.drop_column("shared_quota_reserved")
        batch_op.drop_column("allow_shared_providers")
        batch_op.drop_column("local_fallback_enabled")
        batch_op.drop_column("model_override")
        batch_op.drop_column("preferred_provider")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("local_fallback_enabled")
