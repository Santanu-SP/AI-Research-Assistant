from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.services.auth import SESSION_COOKIE, current_user


def validate_origin(request: Request) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in request.app.state.settings.cors_origins:
            raise AppError("Origin is not allowed", status_code=403, code="origin_not_allowed")


def get_current_user(request: Request, session: Annotated[Session, Depends(get_db)]) -> User:
    validate_origin(request)
    return current_user(session, request.cookies.get(SESSION_COOKIE))


CurrentUser = Annotated[User, Depends(get_current_user)]
