"""FastAPI request dependencies for CSRF origin validation and user authentication."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.services.auth import SESSION_COOKIE, current_user

SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def validate_origin(request: Request) -> None:
    """Enforce allowed Origin header on state-changing HTTP requests."""
    if request.method not in SAFE_HTTP_METHODS:
        origin = request.headers.get("origin")
        if origin and not request.app.state.settings.is_allowed_origin(origin):
            raise AppError(
                "Origin is not allowed",
                status_code=403,
                code="origin_not_allowed",
            )


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> User:
    """Validate request origin and resolve the authenticated ``User`` from cookie."""
    validate_origin(request)
    return current_user(session, request.cookies.get(SESSION_COOKIE))


CurrentUser = Annotated[User, Depends(get_current_user)]