from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import utc_now
from app.models.user import AuthSession, User
from app.services.auth.google import GoogleIdentity, verify_google_identity


def _start_state(client: TestClient) -> str:
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_google_status_does_not_expose_credentials(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/v1/auth/google/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_google_callback_creates_user_and_application_session(anonymous_client: TestClient, monkeypatch) -> None:
    from app.services.auth import google as google_auth

    monkeypatch.setattr(google_auth, "verify_google_identity", lambda *_: GoogleIdentity("google-sub-1", "google@example.com", "Google User"))
    state = _start_state(anonymous_client)
    callback = anonymous_client.get(f"/api/v1/auth/google/callback?state={state}&code=verified-code", follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("/auth/google/complete")
    assert "httponly" in callback.headers["set-cookie"].lower()
    assert anonymous_client.get("/api/v1/auth/me").json()["email"] == "google@example.com"


def test_google_callback_rejects_invalid_state(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/v1/auth/google/callback?state=wrong&code=verified", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/google/complete?oauthError=google_invalid_state")


def test_google_callback_cancellation_returns_to_popup_completion(anonymous_client: TestClient) -> None:
    response = anonymous_client.get(
        "/api/v1/auth/google/callback?error=access_denied",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/google/complete?oauthError=cancelled")


def test_google_login_links_unverified_password_user_and_drops_old_password(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    """Pre-account-takeover guard.

    Anyone can register a password account for an address they do not own.
    When the real owner later proves the address through Google, that
    unverified password and every session created with it must stop working.
    """
    from app.services.auth import google as google_auth

    registered = anonymous_client.post("/api/v1/auth/register", json={"name": "Local", "email": "same@example.com", "password": "long-password-123"})
    assert registered.status_code == 201
    assert anonymous_client.post("/api/v1/auth/login", json={"email": "same@example.com", "password": "long-password-123"}).status_code == 200
    monkeypatch.setattr(google_auth, "verify_google_identity", lambda *_: GoogleIdentity("google-sub-2", "same@example.com", "Google Name"))
    state = _start_state(anonymous_client)
    assert anonymous_client.get(f"/api/v1/auth/google/callback?state={state}&code=verified", follow_redirects=False).status_code == 303
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "same@example.com"))
        assert user is not None and user.google_sub == "google-sub-2"
        assert user.password_hash is None
        assert user.email_verified_at is not None
        # Only the fresh Google session survives.
        assert session.query(AuthSession).filter(AuthSession.user_id == user.id).count() == 1
    assert anonymous_client.get("/api/v1/auth/me").status_code == 200
    assert anonymous_client.post("/api/v1/auth/login", json={"email": "same@example.com", "password": "long-password-123"}).status_code == 401


def test_google_login_keeps_password_of_verified_account(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    from app.services.auth import google as google_auth

    anonymous_client.post("/api/v1/auth/register", json={"name": "Verified", "email": "verified@example.com", "password": "long-password-123"})
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "verified@example.com"))
        assert user is not None
        user.email_verified_at = utc_now()
        session.commit()
    monkeypatch.setattr(google_auth, "verify_google_identity", lambda *_: GoogleIdentity("google-sub-3", "verified@example.com", "Verified"))
    state = _start_state(anonymous_client)
    assert anonymous_client.get(f"/api/v1/auth/google/callback?state={state}&code=verified", follow_redirects=False).status_code == 303
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "verified@example.com"))
        assert user is not None and user.google_sub == "google-sub-3" and user.password_hash is not None


def test_new_google_user_is_marked_verified(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    from app.services.auth import google as google_auth

    monkeypatch.setattr(google_auth, "verify_google_identity", lambda *_: GoogleIdentity("google-sub-4", "fresh@example.com", "Fresh"))
    state = _start_state(anonymous_client)
    anonymous_client.get(f"/api/v1/auth/google/callback?state={state}&code=verified", follow_redirects=False)
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "fresh@example.com"))
        assert user is not None and user.email_verified_at is not None


def test_google_callback_redirects_cleanly_on_unexpected_database_error(
    anonymous_client: TestClient, monkeypatch
) -> None:
    from app.services.auth import google as google_auth

    monkeypatch.setattr(
        google_auth,
        "verify_google_identity",
        lambda *_: GoogleIdentity("google-sub-5", "boom@example.com", "Boom"),
    )

    def raise_schema_error(*_args, **_kwargs):
        raise RuntimeError("column users.local_fallback_enabled does not exist")

    monkeypatch.setattr(google_auth, "resolve_google_user", raise_schema_error)
    state = _start_state(anonymous_client)
    response = anonymous_client.get(
        f"/api/v1/auth/google/callback?state={state}&code=verified",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/google/complete?oauthError=failed")


def test_google_login_rejects_disabled_user(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    from app.services.auth import google as google_auth

    anonymous_client.post(
        "/api/v1/auth/register",
        json={"name": "Disabled", "email": "disabled@example.com", "password": "long-password-123"},
    )
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "disabled@example.com"))
        assert user is not None
        user.is_active = False
        session.commit()

    monkeypatch.setattr(
        google_auth,
        "verify_google_identity",
        lambda *_: GoogleIdentity("google-sub-6", "disabled@example.com", "Disabled"),
    )
    state = _start_state(anonymous_client)
    response = anonymous_client.get(
        f"/api/v1/auth/google/callback?state={state}&code=verified",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/google/complete?oauthError=account_disabled")


def test_verify_google_identity_allows_small_clock_skew(monkeypatch) -> None:
    from app.services.auth import google as google_auth

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        google_auth.httpx,
        "post",
        lambda *_a, **_k: httpx.Response(
            200,
            json={"id_token": "header.payload.sig"},
            request=httpx.Request("POST", google_auth.GOOGLE_TOKEN_URL),
        ),
    )

    def fake_verify(raw_token: str, req: object, audience: str, **kwargs: object) -> dict[str, object]:
        captured["kwargs"] = kwargs
        return {
            "iss": "https://accounts.google.com",
            "email_verified": True,
            "sub": "google-sub-skew",
            "email": "SkewUser@example.com",
            "name": "Skew User",
        }

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", fake_verify)
    settings = Settings(
        _env_file=None,
        app_environment="test",
        google_client_id="client-id",
        google_client_secret="client-secret",
    )
    identity = verify_google_identity("auth-code", settings)
    assert identity == GoogleIdentity("google-sub-skew", "skewuser@example.com", "Skew User")
    assert captured["kwargs"] == {"clock_skew_in_seconds": 10}
