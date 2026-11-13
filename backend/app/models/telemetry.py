from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

json_telemetry_type = JSON().with_variant(JSONB(), "postgresql")


class TelemetryEvent(TimestampMixin, Base):
    """Structured pipeline observability event (never stores sensitive keys or prompts)."""

    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("ix_telemetry_events_category_created", "category", "created_at"),
        Index("ix_telemetry_events_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(json_telemetry_type, nullable=True)

