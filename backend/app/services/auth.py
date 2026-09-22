from datetime import timedelta
from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.models.user import AuthSession, User
from app.schemas.auth import RegisterRequest

SESSION_COOKIE = "ara_session"
password_hasher = PasswordHasher()


def register(session: Session, payload: RegisterRequest) -> User:
    if session.scalar(select(User.id).where(User.email == payload.email)):
        raise AppError("An account with this email already exists", status_code=409, code="email_taken")
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=password_hasher.hash(payload.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError("An account with this email already exists", status_code=409, code="email_taken") from exc
    session.refresh(user)
    return user


def login(session: Session, email: str, password: str, session_days: int) -> tuple[User, str]:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    try:
        valid = bool(user and user.is_active and user.password_hash and password_hasher.verify(user.password_hash, password))
    except (VerifyMismatchError, VerificationError):
        valid = False
    if not valid or user is None:
        raise AppError("Incorrect email or password", status_code=401, code="invalid_credentials")
    token = create_session(session, user, session_days)
    return user, token


def create_session(session: Session, user: User, session_days: int) -> str:
    """Create one opaque, revocable application session for any verified identity."""
    token = secrets.token_urlsafe(48)
    session.add(AuthSession(
        token_hash=sha256(token.encode()).hexdigest(),
        user_id=user.id,
        expires_at=utc_now() + timedelta(days=session_days),
    ))
    session.commit()
    return token


def current_user(session: Session, token: str | None) -> User:
    if not token:
        raise AppError("Authentication required", status_code=401, code="authentication_required")
    auth_session = session.get(AuthSession, sha256(token.encode()).hexdigest())
    if auth_session is None or auth_session.expires_at <= utc_now():
        raise AppError("Session expired or invalid", status_code=401, code="session_invalid")
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise AppError("Session expired or invalid", status_code=401, code="session_invalid")
    return user


def logout(session: Session, token: str | None) -> None:
    if token:
        auth_session = session.get(AuthSession, sha256(token.encode()).hexdigest())
        if auth_session is not None:
            session.delete(auth_session)
            session.commit()
