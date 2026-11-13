"""Background job status and telemetry summary routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.errors import AppError
from app.db.session import get_db
from app.models.document import Document
from app.models.research import Research
from app.schemas.base import ApiSchema
from app.services.jobs import queue as job_queue
from app.services.observability.telemetry import summarize_telemetry

router = APIRouter(tags=["jobs & telemetry"])
DatabaseSession = Annotated[Session, Depends(get_db)]


class BackgroundJobStatusResponse(ApiSchema):
    id: UUID
    kind: str
    target_id: UUID
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


@router.get("/jobs/{job_id}", response_model=BackgroundJobStatusResponse)
def get_job_status(
    job_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
) -> BackgroundJobStatusResponse:
    job = job_queue.get_job(session, job_id)
    if job is None:
        raise AppError("Background job not found", status_code=404, code="job_not_found")

    # Verify ownership of target resource
    if job.kind in job_queue.DOCUMENT_JOB_KINDS:
        doc = session.get(Document, job.target_id)
        if doc is None or doc.user_id != user.id:
            raise AppError("Background job not found", status_code=404, code="job_not_found")
    elif job.kind == job_queue.RUN_RESEARCH:
        run = session.get(Research, job.target_id)
        if run is None or run.user_id != user.id:
            raise AppError("Background job not found", status_code=404, code="job_not_found")

    return BackgroundJobStatusResponse.model_validate(job)


@router.get("/telemetry/summary")
def get_telemetry_summary(
    session: DatabaseSession,
    user: CurrentUser,
) -> dict[str, Any]:
    return summarize_telemetry(session, user_id=user.id)
