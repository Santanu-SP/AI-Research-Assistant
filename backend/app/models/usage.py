"""Database models for atomic shared-key quota enforcement and model usage rollups."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class DailyQuotaUsage(TimestampMixin, Base):
    """Atomic per-day counters for the shared server API request pool and each user."""

    __tablename__ = "daily_quota_usage"
    __table_args__ = (
        UniqueConstraint("usage_date", "scope_key", name="uq_daily_quota_usage_date_scope"),
        CheckConstraint("shared_requests_used >= 0", name="ck_daily_quota_usage_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    shared_requests_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )


class ModelUsageDaily(TimestampMixin, Base):
    """Compact daily rollup of LLM requests and tokens per user, provider, model, and source."""

    __tablename__ = "model_usage_daily"
    __table_args__ = (
        UniqueConstraint(
            "usage_date",
            "user_id",
            "provider",
            "model_name",
            "usage_source",
            name="uq_model_usage_daily_bucket",
        ),
        CheckConstraint("request_count >= 0", name="ck_model_usage_daily_request_count_nonnegative"),
        Index("ix_model_usage_daily_user_date", "user_id", "usage_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    usage_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_source: Mapped[str] = mapped_column(
        String(16),
        default="shared",
        server_default="shared",
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    estimated_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    last_used_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
