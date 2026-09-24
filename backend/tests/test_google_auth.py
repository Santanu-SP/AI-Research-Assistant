from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.user import User
from app.services.google_auth import GoogleIdentity


def _start_state(client: TestClient) -> str:
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_google_callback_creates_user_and_application_session(anonymous_client: TestClient, monkeypatch) -> None:
    from app.services import google_auth

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


def test_google_login_links_existing_password_user(anonymous_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch) -> None:
    from app.services import google_auth

    registered = anonymous_client.post("/api/v1/auth/register", json={"name": "Local", "email": "same@example.com", "password": "long-password-123"})
    assert registered.status_code == 201
    monkeypatch.setattr(google_auth, "verify_google_identity", lambda *_: GoogleIdentity("google-sub-2", "same@example.com", "Google Name"))
    state = _start_state(anonymous_client)
    assert anonymous_client.get(f"/api/v1/auth/google/callback?state={state}&code=verified", follow_redirects=False).status_code == 303
    with db_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "same@example.com"))
        assert user is not None and user.google_sub == "google-sub-2" and user.password_hash is not None
