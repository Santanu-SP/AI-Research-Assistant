from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class UserAPIKey(TimestampMixin, Base):
    """Encrypted user-supplied AI provider API keys (BYOK)."""

    __tablename__ = "user_api_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
        Index("ix_user_api_keys_user_active", "user_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    usage_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    usage_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
    )


class UserModelPreference(TimestampMixin, Base):
    """Persisted per-user preferred model choice for each LLM provider."""

    __tablename__ = "user_model_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_model_prefs_user_provider"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)

