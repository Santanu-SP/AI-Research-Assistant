"""Persistence models for multi-user project/research collaboration and invites."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.project import ResearchProject
    from app.models.research import Research
    from app.models.user import User


class ProjectMember(TimestampMixin, Base):
    """Explicit collaborator membership on a shared research project."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_project_members_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    invited_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped[ResearchProject] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class ResearchMember(TimestampMixin, Base):
    """Explicit collaborator membership on an individual research chat/report."""

    __tablename__ = "research_members"
    __table_args__ = (
        UniqueConstraint("research_id", "user_id", name="uq_research_members_research_user"),
        CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_research_members_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    invited_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    research: Mapped[Research] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class CollaborationInvite(TimestampMixin, Base):
    """Shareable link or email-bound invite to join a project or research run."""

    __tablename__ = "collaboration_invites"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('project', 'research')",
            name="ck_collaboration_invites_resource_type",
        ),
        CheckConstraint(
            "role IN ('editor', 'viewer')",
            name="ck_collaboration_invites_role",
        ),
        CheckConstraint(
            "max_uses IS NULL OR max_uses >= 1",
            name="ck_collaboration_invites_max_uses_positive",
        ),
        CheckConstraint(
            "use_count >= 0",
            name="ck_collaboration_invites_use_count_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    resource_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    research_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    target_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
