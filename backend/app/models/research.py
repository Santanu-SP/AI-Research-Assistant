from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime
from app.domain.research import ResearchDepth, ResearchStatus


def _enum_values(enum_class: type[ResearchDepth] | type[ResearchStatus]) -> list[str]:
    return [member.value for member in enum_class]


research_depth_enum = Enum(
    ResearchDepth,
    name="research_depth",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

research_status_enum = Enum(
    ResearchStatus,
    name="research_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)


class Research(TimestampMixin, Base):
    __tablename__ = "research"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[ResearchStatus] = mapped_column(
        research_status_enum,
        default=ResearchStatus.DRAFT,
        server_default=ResearchStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    research_depth: Mapped[ResearchDepth] = mapped_column(
        research_depth_enum,
        default=ResearchDepth.STANDARD,
        server_default=ResearchDepth.STANDARD.value,
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
        index=True,
    )
