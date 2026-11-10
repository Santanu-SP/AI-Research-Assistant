from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class BackgroundJob(TimestampMixin, Base):
    """One unit of deferred work, claimed by the in-process worker.

    The table doubles as a small durable queue: rows survive restarts, a
    crashed run is noticed through ``locked_at`` and retried, and PostgreSQL
    claims use ``FOR UPDATE SKIP LOCKED`` so several API processes can share
    the same queue safely.
    """

    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_background_jobs_state_run_after", "state", "run_after"),
        Index("ix_background_jobs_target", "kind", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # queued -> running -> succeeded | failed
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
