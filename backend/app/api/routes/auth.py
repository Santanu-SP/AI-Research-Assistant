"""Authentication API endpoints for registration, login, Google OAuth, and logout."""

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

SECONDS_PER_DAY = 86_400
AUTH_COOKIE_PATH = "/api/v1"


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    """Attach the HTTP-only opaque session cookie to the outgoing response."""
    settings = request.app.state.settings
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_days * SECONDS_PER_DAY,
        path=AUTH_COOKIE_PATH,
    )


def _google_complete_url(request: Request, oauth_error: str | None = None) -> str:
    """Build the frontend redirect URL for Google OAuth completion or error display."""
    base = f"{request.app.state.settings.frontend_url.rstrip('/')}/auth/google/complete"
    if not oauth_error:
        return base
    query = urlencode({"oauthError": oauth_error})
    return f"{base}?{query}"


def _google_error_redirect(request: Request, code: str) -> RedirectResponse:
    """Redirect the browser back to the frontend with an OAuth error code."""
    return RedirectResponse(
        _google_complete_url(request, oauth_error=code),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    session: DatabaseSession,
    request: Request,
) -> UserResponse:
    """Register a new user account."""
    validate_origin(request)
    return auth_service.register(session, payload)


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    session: DatabaseSession,
    request: Request,
    response: Response,
) -> UserResponse:
    """Authenticate with email and password and set the session cookie."""
    validate_origin(request)
    user, token = auth_service.login(
        session,
        payload.email,
        payload.password,
        request.app.state.settings.auth_session_days,
    )
    _set_session_cookie(response, token, request)
    return user


@router.get("/google/start")
def google_start(session: DatabaseSession, request: Request) -> RedirectResponse:
    """Initiate the Google OAuth 2.0 authorization code flow."""
    return RedirectResponse(
        google_auth.start_url(session, request.app.state.settings),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/google/status")
def google_status(request: Request) -> dict[str, bool]:
    """Expose only whether optional Google OAuth is enabled; never expose credentials."""
    return {"enabled": google_auth.is_configured(request.app.state.settings)}


@router.get("/google/callback")
def google_callback(
    session: DatabaseSession,
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the Google OAuth callback, verify identity, and establish a session."""
    if error or not code:
        error_code = "cancelled" if error == "access_denied" else "failed"
        return _google_error_redirect(request, error_code)

    try:
        settings = request.app.state.settings
        google_auth.consume_state(session, state)
        identity = google_auth.verify_google_identity(code, settings)
        user = google_auth.resolve_google_user(session, identity)
        token = auth_service.create_session(
            session,
            user,
            settings.auth_session_days,
        )
    except AppError as exc:
        return _google_error_redirect(request, exc.code)

    response = RedirectResponse(
        _google_complete_url(request),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _set_session_cookie(response, token, request)
    return response


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: DatabaseSession,
    request: Request,
    response: Response,
) -> None:
    """Revoke the current session and clear the session cookie."""
    validate_origin(request)
    auth_service.logout(session, request.cookies.get(auth_service.SESSION_COOKIE))
    response.delete_cookie(auth_service.SESSION_COOKIE, path=AUTH_COOKIE_PATH)