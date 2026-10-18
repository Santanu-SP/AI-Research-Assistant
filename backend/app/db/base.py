from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.types import UTCDateTime


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    """Return string values for a StrEnum to bind SQLAlchemy Enum constraints."""
    return [member.value for member in enum_class]


def make_str_enum(enum_class: type[StrEnum], *, name: str) -> Enum:
    """Create a consistent non-native SQLAlchemy Enum with check constraints."""
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=enum_values,
    )


def commit_or_raise(
    session: Session,
    *,
    message: str,
    code: str,
    status_code: int = 500,
) -> None:
    """Commit the active session or rollback and raise a structured AppError."""
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(message, status_code=status_code, code=code) from exc


class Base(DeclarativeBase):
    """Declarative base for all persisted application models."""


class TimestampMixin:
    """Consistent UTC timestamps for persisted models."""

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