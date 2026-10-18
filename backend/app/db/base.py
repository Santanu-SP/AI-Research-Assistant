"""Declarative SQLAlchemy base class, timestamp mixin, and enum helper."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time import utc_now
from app.db.types import UTCDateTime


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    """Extract string values from a ``StrEnum`` for SQLAlchemy Enum column persistence."""
    return [member.value for member in enum_class]


class Base(DeclarativeBase):
    """Declarative base for all persisted application models."""


class TimestampMixin:
    """Consistent UTC ``created_at`` and ``updated_at`` columns for persisted models."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )