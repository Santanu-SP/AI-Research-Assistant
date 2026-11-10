"""Enqueue, claim, and settle rows in ``background_jobs``."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.job import BackgroundJob

INGEST_DOCUMENT = "ingest_document"
RUN_RESEARCH = "run_research"

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    kind: str
    target_id: UUID
    attempts: int


def enqueue(session: Session, kind: str, target_id: UUID, *, commit: bool = True) -> BackgroundJob:
    job = BackgroundJob(kind=kind, target_id=target_id, state=QUEUED, attempts=0, run_after=utc_now())
    session.add(job)
    if commit:
        session.commit()
    return job


def claim_next(session: Session) -> ClaimedJob | None:
    """Atomically move the oldest runnable job to ``running``.

    PostgreSQL uses ``FOR UPDATE SKIP LOCKED`` so concurrent workers never
    take the same row. SQLite ignores the lock hint, so the guarded UPDATE
    (``state = 'queued'``) is what keeps a second claimer out there.
    """
    now = utc_now()
    candidate = session.scalar(
        select(BackgroundJob.id)
        .where(BackgroundJob.state == QUEUED, BackgroundJob.run_after <= now)
        .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if candidate is None:
        session.rollback()
        return None
    result = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == candidate, BackgroundJob.state == QUEUED)
        .values(
            state=RUNNING,
            locked_at=now,
            attempts=BackgroundJob.attempts + 1,
            updated_at=now,
        )
    )
    session.commit()
    if result.rowcount != 1:
        return None
    job = session.get(BackgroundJob, candidate)
    if job is None:
        return None
    return ClaimedJob(id=job.id, kind=job.kind, target_id=job.target_id, attempts=job.attempts)


def mark_succeeded(session: Session, job_id: UUID) -> None:
    session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .values(state=SUCCEEDED, locked_at=None, last_error=None, updated_at=utc_now())
    )
    session.commit()


def mark_failed(
    session: Session,
    job_id: UUID,
    error: str,
    *,
    retry_in_seconds: float | None = None,
) -> None:
    """Fail a job, or put it back in the queue when a retry delay is given."""
    now = utc_now()
    values: dict[str, object] = {"locked_at": None, "last_error": error[:2000], "updated_at": now}
    if retry_in_seconds is None:
        values["state"] = FAILED
    else:
        values["state"] = QUEUED
        values["run_after"] = now + timedelta(seconds=retry_in_seconds)
    session.execute(update(BackgroundJob).where(BackgroundJob.id == job_id).values(**values))
    session.commit()


def stale_running_jobs(session: Session, stale_after_seconds: int) -> list[BackgroundJob]:
    cutoff = utc_now() - timedelta(seconds=stale_after_seconds)
    return list(
        session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.state == RUNNING,
                BackgroundJob.locked_at <= cutoff,
            )
        ).all()
    )


def has_active_job(session: Session, kind: str, target_id: UUID) -> bool:
    return (
        session.scalar(
            select(BackgroundJob.id).where(
                BackgroundJob.kind == kind,
                BackgroundJob.target_id == target_id,
                BackgroundJob.state.in_((QUEUED, RUNNING)),
            ).limit(1)
        )
        is not None
    )
