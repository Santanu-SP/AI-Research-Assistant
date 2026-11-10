from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.services.auth.sessions import SESSION_COOKIE, current_user


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _referer_origin(referer: str | None) -> str | None:
    if not referer:
        return None
    parts = urlsplit(referer)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def validate_origin(request: Request) -> None:
    """Reject cross-site state-changing requests (CSRF defence).

    Browsers attach ``Origin`` to cross-site POST/PATCH/DELETE requests. When
    it is missing we fall back to ``Referer``; when both are missing the
    request did not come from our frontend, so it is refused unless the
    deployment explicitly turns that requirement off.
    """
    if request.method in SAFE_METHODS:
        return
    settings = request.app.state.settings
    origin = request.headers.get("origin") or _referer_origin(request.headers.get("referer"))
    if origin is None:
        if settings.require_origin_header:
            raise AppError(
                "Origin header is required",
                status_code=403,
                code="origin_required",
            )
        return
    if not settings.is_allowed_origin(origin):
        raise AppError("Origin is not allowed", status_code=403, code="origin_not_allowed")


def get_current_user(request: Request, session: Annotated[Session, Depends(get_db)]) -> User:
    validate_origin(request)
    return current_user(session, request.cookies.get(SESSION_COOKIE))


CurrentUser = Annotated[User, Depends(get_current_user)]
