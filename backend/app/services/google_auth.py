"""Google OpenID Connect code-flow helpers.

Google tokens only exist transiently during callback validation.  The app keeps
only its own opaque session token, hashed in ``auth_sessions``.
"""

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import secrets
from urllib.parse import urlencode

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.models.user import OAuthState, User

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


def _google_is_configured(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def start_url(session: Session, settings: Settings) -> str:
    if not _google_is_configured(settings):
        raise AppError("Google sign-in is not configured", status_code=503, code="google_not_configured")
    state = secrets.token_urlsafe(32)
    session.add(OAuthState(
        state_hash=sha256(state.encode()).hexdigest(),
        expires_at=utc_now() + timedelta(minutes=settings.google_oauth_state_minutes),
    ))
    session.commit()
    query = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return f"{GOOGLE_AUTHORIZATION_URL}?{query}"


def consume_state(session: Session, state: str | None) -> None:
    if not state:
        raise AppError("Google sign-in could not be verified", status_code=400, code="google_invalid_state")
    record = session.get(OAuthState, sha256(state.encode()).hexdigest())
    if record is None or record.expires_at <= utc_now():
        if record is not None:
            session.delete(record)
            session.commit()
        raise AppError("Google sign-in could not be verified", status_code=400, code="google_invalid_state")
    session.delete(record)
    session.commit()


def verify_google_identity(code: str, settings: Settings) -> GoogleIdentity:
    """Exchange a callback code and cryptographically verify the resulting ID token."""
    if not _google_is_configured(settings):
        raise AppError("Google sign-in is not configured", status_code=503, code="google_not_configured")
    try:
        token_response = httpx.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=10)
        token_response.raise_for_status()
        raw_id_token = token_response.json().get("id_token")
        if not isinstance(raw_id_token, str):
            raise ValueError("Google did not return an ID token")
        claims = id_token.verify_oauth2_token(raw_id_token, GoogleRequest(), settings.google_client_id)
    except Exception as exc:  # Provider and cryptographic failures intentionally share a safe response.
        raise AppError("Google sign-in could not be completed", status_code=401, code="google_verification_failed") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS or claims.get("email_verified") is not True:
        raise AppError("Google account email must be verified", status_code=401, code="google_unverified_email")
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not isinstance(email, str):
        raise AppError("Google did not provide a verified identity", status_code=401, code="google_identity_incomplete")
    name = claims.get("name")
    return GoogleIdentity(subject=subject, email=email.strip().lower(), name=name.strip() if isinstance(name, str) and name.strip() else email.split("@", 1)[0])


def resolve_google_user(session: Session, identity: GoogleIdentity) -> User:
    existing_subject = session.scalar(select(User).where(User.google_sub == identity.subject))
    if existing_subject is not None:
        if existing_subject.email != identity.email:
            raise AppError("Google identity conflicts with this account", status_code=409, code="google_identity_conflict")
        return existing_subject
    user = session.scalar(select(User).where(User.email == identity.email))
    if user is None:
        user = User(name=identity.name, email=identity.email, password_hash=None, google_sub=identity.subject)
        session.add(user)
    elif user.google_sub is None:
        user.google_sub = identity.subject
    else:
        raise AppError("Google identity conflicts with this account", status_code=409, code="google_identity_conflict")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError("Google identity conflicts with this account", status_code=409, code="google_identity_conflict") from exc
    session.refresh(user)
    return user
