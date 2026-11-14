from datetime import timedelta
from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.models.user import AuthSession, OAuthState, User
from app.schemas.auth import RegisterRequest

SESSION_COOKIE = "ara_session"
password_hasher = PasswordHasher()
# Verified against when the account does not exist (or has no password), so a
# failed login costs the same Argon2 time either way and response timing does
# not reveal which emails are registered.
_TIMING_EQUALIZER_HASH = password_hasher.hash("timing-equalizer-not-a-real-password")


def register(session: Session, payload: RegisterRequest) -> User:
    existing = session.scalar(select(User.id).where(User.email == payload.email))
    if existing:
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


def _password_matches(user: User | None, password: str) -> bool:
    if user is None or not user.is_active or not user.password_hash:
        try:
            password_hasher.verify(_TIMING_EQUALIZER_HASH, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False
    try:
        return bool(password_hasher.verify(user.password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def login(
    session: Session,
    email: str,
    password: str,
    session_days: int,
    *,
    max_sessions: int | None = None,
    inactivity_days: int | None = None,
) -> tuple[User, str]:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if not _password_matches(user, password) or user is None:
        raise AppError(
            "Incorrect email or password",
            status_code=401,
            code="invalid_credentials",
        )
    token = create_session(
        session,
        user,
        session_days,
        max_sessions=max_sessions,
        inactivity_days=inactivity_days,
    )
    return user, token


def create_session(
    session: Session,
    user: User,
    session_days: int,
    *,
    max_sessions: int | None = None,
    inactivity_days: int | None = None,
) -> str:
    """Create one opaque, revocable application session for any verified identity.

    When ``max_sessions`` is set, the user's oldest sessions beyond that cap
    are revoked so repeated logins cannot grow the table without bound.
    """
    token = secrets.token_urlsafe(48)
    now = utc_now()
    effective_days = min(session_days, inactivity_days) if inactivity_days is not None else session_days
    session.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.expires_at <= now,
        )
    )
    session.add(
        AuthSession(
            token_hash=sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=now + timedelta(days=effective_days),
            created_at=now,
        )
    )
    session.flush()
    if max_sessions is not None:
        keep = select(AuthSession.token_hash).where(AuthSession.user_id == user.id).order_by(
            AuthSession.created_at.desc(), AuthSession.token_hash
        ).limit(max_sessions)
        session.execute(
            delete(AuthSession).where(
                AuthSession.user_id == user.id,
                AuthSession.token_hash.not_in(keep.scalar_subquery()),
            ).execution_options(synchronize_session=False)
        )
    session.commit()
    return token


def current_user(
    session: Session,
    token: str | None,
    *,
    session_days: int | None = None,
    inactivity_days: int | None = None,
) -> User:
    if not token:
        raise AppError(
            "Authentication required",
            status_code=401,
            code="authentication_required",
        )
    auth_session = session.get(AuthSession, sha256(token.encode()).hexdigest())
    now = utc_now()
    hard_expired = (
        session_days is not None
        and auth_session is not None
        and auth_session.created_at + timedelta(days=session_days) <= now
    )
    if auth_session is None or auth_session.expires_at <= now or hard_expired:
        if auth_session is not None:
            session.delete(auth_session)
            session.commit()
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
    if inactivity_days is not None:
        idle_target = now + timedelta(days=inactivity_days)
        if session_days is not None:
            idle_target = min(idle_target, auth_session.created_at + timedelta(days=session_days))
        if idle_target - auth_session.expires_at >= timedelta(hours=1):
            auth_session.expires_at = idle_target
            session.commit()
    return user


def logout(session: Session, token: str | None) -> None:
    if token:
        auth_session = session.get(AuthSession, sha256(token.encode()).hexdigest())
        if auth_session is not None:
            session.delete(auth_session)
            session.commit()


def logout_everywhere(session: Session, user: User) -> int:
    """Revoke every session belonging to ``user``; returns how many."""
    result = session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    session.commit()
    return int(result.rowcount or 0)


def purge_expired(session: Session) -> tuple[int, int]:
    """Delete expired sessions and OAuth states; returns (sessions, states)."""
    now = utc_now()
    sessions_removed = session.execute(
        delete(AuthSession).where(AuthSession.expires_at <= now)
    ).rowcount
    states_removed = session.execute(
        delete(OAuthState).where(OAuthState.expires_at <= now)
    ).rowcount
    session.commit()
    return int(sessions_removed or 0), int(states_removed or 0)
