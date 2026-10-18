"""User registration, Argon2 password verification, and opaque session management."""

from datetime import timedelta
from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.models.user import AuthSession, User
from app.schemas.auth import RegisterRequest

SESSION_COOKIE = "ara_session"
SESSION_TOKEN_BYTES = 48
password_hasher = PasswordHasher()


def _hash_session_token(token: str) -> str:
    """Compute the SHA-256 hex digest of an opaque session token."""
    return sha256(token.encode()).hexdigest()


def _verify_user_password(user: User | None, password: str) -> bool:
    """Safely verify a plaintext password against a user's Argon2 password hash."""
    if user is None or not user.is_active or not user.password_hash:
        return False
    try:
        return bool(password_hasher.verify(user.password_hash, password))
    except (VerifyMismatchError, VerificationError):
        return False


def register(session: Session, payload: RegisterRequest) -> User:
    """Register a new user account after checking for duplicate email addresses."""
    existing_id = session.scalar(select(User.id).where(User.email == payload.email))
    if existing_id:
        raise AppError(
            "An account with this email already exists",
            status_code=409,
            code="email_taken",
        )

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
        raise AppError(
            "An account with this email already exists",
            status_code=409,
            code="email_taken",
        ) from exc

    session.refresh(user)
    return user


def login(
    session: Session,
    email: str,
    password: str,
    session_days: int,
) -> tuple[User, str]:
    """Authenticate a user by email and password and issue a new opaque session token."""
    normalized_email = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized_email))

    if not _verify_user_password(user, password) or user is None:
        raise AppError(
            "Incorrect email or password",
            status_code=401,
            code="invalid_credentials",
        )

    token = create_session(session, user, session_days)
    return user, token


def create_session(session: Session, user: User, session_days: int) -> str:
    """Create one opaque, revocable application session for any verified identity."""
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    session.add(
        AuthSession(
            token_hash=_hash_session_token(token),
            user_id=user.id,
            expires_at=utc_now() + timedelta(days=session_days),
        )
    )
    session.commit()
    return token


def current_user(session: Session, token: str | None) -> User:
    """Resolve the active ``User`` from a session cookie token or raise 401."""
    if not token:
        raise AppError(
            "Authentication required",
            status_code=401,
            code="authentication_required",
        )

    auth_session = session.get(AuthSession, _hash_session_token(token))
    if auth_session is None or auth_session.expires_at <= utc_now():
        raise AppError(
            "Session expired or invalid",
            status_code=401,
            code="session_invalid",
        )

    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise AppError(
            "Session expired or invalid",
            status_code=401,
            code="session_invalid",
        )
    return user


def logout(session: Session, token: str | None) -> None:
    """Revoke the server-side session matching the provided token if present."""
    if not token:
        return
    auth_session = session.get(AuthSession, _hash_session_token(token))
    if auth_session is not None:
        session.delete(auth_session)
        session.commit()