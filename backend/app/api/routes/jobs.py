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
from app.domain.collaboration import CollaboratorRole
from app.schemas.base import ApiSchema
from app.services.collaboration.access import require_document_access, require_research_access
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

    # Verify collaborator/owner access of target resource
    if job.kind in job_queue.DOCUMENT_JOB_KINDS:
        try:
            require_document_access(
                session, job.target_id, user.id, min_role=CollaboratorRole.VIEWER
            )
        except AppError as exc:
            raise AppError(
                "Background job not found", status_code=404, code="job_not_found"
            ) from exc
    elif job.kind == job_queue.RUN_RESEARCH:
        try:
            require_research_access(
                session, job.target_id, user.id, min_role=CollaboratorRole.VIEWER
            )
        except AppError as exc:
            raise AppError(
                "Background job not found", status_code=404, code="job_not_found"
            ) from exc

    return BackgroundJobStatusResponse.model_validate(job)


@router.get("/telemetry/summary")
def get_telemetry_summary(
    session: DatabaseSession,
    user: CurrentUser,
) -> dict[str, Any]:
    return summarize_telemetry(session, user_id=user.id)
