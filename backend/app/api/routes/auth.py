from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, validate_origin
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[Session, Depends(get_db)]


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
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        httponly=True,
        secure=request.app.state.settings.auth_cookie_secure,
        samesite="lax",
        max_age=request.app.state.settings.auth_session_days * 86400,
        path="/api/v1",
    )
    return user


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: DatabaseSession, request: Request, response: Response) -> None:
    validate_origin(request)
    auth_service.logout(session, request.cookies.get(auth_service.SESSION_COOKIE))
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/api/v1")
