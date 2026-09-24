from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, validate_origin
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services import auth as auth_service
from app.services import google_auth

router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        auth_service.SESSION_COOKIE, token, httponly=True,
        secure=request.app.state.settings.auth_cookie_secure, samesite="lax",
        max_age=request.app.state.settings.auth_session_days * 86400, path="/api/v1",
    )


def _google_error_redirect(request: Request, code: str) -> RedirectResponse:
    query = urlencode({"oauthError": code})
    return RedirectResponse(
        f"{request.app.state.settings.frontend_url.rstrip('/')}/auth/google/complete?{query}",
        status_code=303,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: DatabaseSession, request: Request) -> UserResponse:
    validate_origin(request)
    return auth_service.register(session, payload)


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, session: DatabaseSession, request: Request, response: Response) -> UserResponse:
    validate_origin(request)
    user, token = auth_service.login(
        session, payload.email, payload.password, request.app.state.settings.auth_session_days
    )
    _set_session_cookie(response, token, request)
    return user


@router.get("/google/start")
def google_start(session: DatabaseSession, request: Request) -> RedirectResponse:
    return RedirectResponse(google_auth.start_url(session, request.app.state.settings), status_code=303)


@router.get("/google/callback")
def google_callback(
    session: DatabaseSession,
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error or not code:
        return _google_error_redirect(request, "cancelled" if error == "access_denied" else "failed")
    try:
        google_auth.consume_state(session, state)
        identity = google_auth.verify_google_identity(code, request.app.state.settings)
        user = google_auth.resolve_google_user(session, identity)
        token = auth_service.create_session(session, user, request.app.state.settings.auth_session_days)
    except AppError as exc:
        return _google_error_redirect(request, exc.code)
    response = RedirectResponse(
        f"{request.app.state.settings.frontend_url.rstrip('/')}/auth/google/complete",
        status_code=303,
    )
    _set_session_cookie(response, token, request)
    return response


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: DatabaseSession, request: Request, response: Response) -> None:
    validate_origin(request)
    auth_service.logout(session, request.cookies.get(auth_service.SESSION_COOKIE))
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/api/v1")
