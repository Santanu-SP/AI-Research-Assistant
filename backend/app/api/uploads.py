from uuid import UUID

from fastapi import Request, status

from app.core import rate_limit
from app.domain.documents import DocumentStatus
from app.models.document import Document


def enforce_upload_rate_limit(request: Request, user_id: UUID) -> None:
    rate_limit.enforce(
        request,
        "upload",
        key=str(user_id),
        limit=request.app.state.settings.rate_limit_upload_per_minute,
        window_seconds=60,
    )


def upload_status_code(document: Document) -> int:
    """201 when the document is finished, 202 when processing continues later."""
    if document.status in (DocumentStatus.UPLOADED, DocumentStatus.PROCESSING):
        return status.HTTP_202_ACCEPTED
    return status.HTTP_201_CREATED
