"""Add multi-user project/research collaboration tables, invites, attribution, and versions.

Revision ID: 0022_collaboration_realtime
Revises: 0021_report_followups
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0022_collaboration_realtime"
down_revision: str | None = "0021_report_followups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_projects",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "research",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    with op.batch_alter_table("report_followups") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_report_followups_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_report_followups_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "project_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_project_members_role"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index(
        op.f("ix_project_members_project_id"),
        "project_members",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_members_user_id"),
        "project_members",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "research_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_research_members_role"),
        sa.ForeignKeyConstraint(
            ["research_id"],
            ["research.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_id", "user_id", name="uq_research_members_research_user"),
    )
    op.create_index(
        op.f("ix_research_members_research_id"),
        "research_members",
        ["research_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_members_user_id"),
        "research_members",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "collaboration_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=16), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("research_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("target_email", sa.String(length=320), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "resource_type IN ('project', 'research')",
            name="ck_collaboration_invites_resource_type",
        ),
        sa.CheckConstraint(
            "role IN ('editor', 'viewer')",
            name="ck_collaboration_invites_role",
        ),
        sa.CheckConstraint(
            "max_uses IS NULL OR max_uses >= 1",
            name="ck_collaboration_invites_max_uses_positive",
        ),
        sa.CheckConstraint(
            "use_count >= 0",
            name="ck_collaboration_invites_use_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_id"],
            ["research.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_collaboration_invites_token_hash"),
    )
    op.create_index(
        op.f("ix_collaboration_invites_resource_type"),
        "collaboration_invites",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collaboration_invites_project_id"),
        "collaboration_invites",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collaboration_invites_research_id"),
        "collaboration_invites",
        ["research_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collaboration_invites_target_email"),
        "collaboration_invites",
        ["target_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collaboration_invites_expires_at"),
        "collaboration_invites",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_collaboration_invites_expires_at"), table_name="collaboration_invites")
    op.drop_index(op.f("ix_collaboration_invites_target_email"), table_name="collaboration_invites")
    op.drop_index(op.f("ix_collaboration_invites_research_id"), table_name="collaboration_invites")
    op.drop_index(op.f("ix_collaboration_invites_project_id"), table_name="collaboration_invites")
    op.drop_index(op.f("ix_collaboration_invites_resource_type"), table_name="collaboration_invites")
    op.drop_table("collaboration_invites")

    op.drop_index(op.f("ix_research_members_user_id"), table_name="research_members")
    op.drop_index(op.f("ix_research_members_research_id"), table_name="research_members")
    op.drop_table("research_members")

    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")

    with op.batch_alter_table("report_followups") as batch_op:
        batch_op.drop_index(op.f("ix_report_followups_user_id"))
        batch_op.drop_constraint("fk_report_followups_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    op.drop_column("research", "version")
    op.drop_column("research_projects", "version")
