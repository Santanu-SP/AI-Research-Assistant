"""Security and reliability guarantees added in the hardening pass."""

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DEV_BYOK_ENCRYPTION_SECRET, Settings
from app.core.time import utc_now
from app.main import create_app
from app.models.user import AuthSession, OAuthState, User
from app.services.auth import sessions as auth_sessions
from conftest import FRONTEND_HEADERS, FRONTEND_ORIGIN


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        app_environment="test",
        database_url=f"sqlite:///{tmp_path / 'hardening.db'}",
        cors_origins=[FRONTEND_ORIGIN],
        document_upload_dir=tmp_path / "uploads",
        document_max_upload_bytes=1024 * 1024,
        document_chunk_size=256,
        document_chunk_overlap=32,
        document_ingestion_backend="legacy",
        embedding_enabled=False,
        ingestion_mode="inline",
        worker_enabled=False,
        rate_limit_enabled=False,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def make_client(tmp_path: Path):
    from app.db.base import Base

    created = []

    def factory(**overrides) -> TestClient:
        application = create_app(_settings(tmp_path, **overrides))
        Base.metadata.create_all(application.state.db_engine)
        client = TestClient(application, headers=FRONTEND_HEADERS, raise_server_exceptions=False)
        client.__enter__()
        created.append((client, application))
        return client

    yield factory
    for client, application in created:
        client.__exit__(None, None, None)
        Base.metadata.drop_all(application.state.db_engine)


def _register_and_login(client: TestClient, email: str = "user@example.com") -> None:
    password = "long-password-123"
    assert client.post("/api/v1/auth/register", json={"name": "User", "email": email, "password": password}).status_code == 201
    assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200


# --- settings & secure defaults ------------------------------------------


def test_settings_default_to_production_with_secure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    # Check the built-in defaults, not whatever the shell or CI exports.
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_environment == "production"
    assert settings.auth_cookie_secure is True
    assert settings.api_docs_enabled is False
    assert settings.effective_cors_origin_regex is None


def test_production_refuses_explicitly_insecure_cookies() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_environment="production", auth_cookie_secure=False)


def test_development_does_not_trust_lan_origins_unless_opted_in() -> None:
    settings = Settings(_env_file=None, app_environment="development")
    assert settings.auth_cookie_secure is False
    assert not settings.is_allowed_origin("http://192.168.1.50:5173")


_TEST_PROD_BYOK_KEY = ("test-" * 4) + "byok-key"


def test_production_refuses_missing_or_default_byok_encryption_secret(make_client) -> None:
    with pytest.raises(ValueError, match="API_KEY_ENCRYPTION_SECRET"):
        Settings(
            _env_file=None,
            app_environment="production",
            auth_cookie_secure=True,
            api_key_encryption_secret=DEV_BYOK_ENCRYPTION_SECRET,
        )

    with pytest.raises(ValueError, match="API_KEY_ENCRYPTION_SECRET"):
        make_client(app_environment="production", auth_cookie_secure=True)


def test_docs_are_hidden_in_production(make_client) -> None:
    client = make_client(
        app_environment="production",
        auth_cookie_secure=True,
        api_key_encryption_secret=_TEST_PROD_BYOK_KEY,
    )
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_are_available_outside_production(make_client) -> None:
    assert make_client().get("/openapi.json").status_code == 200


# --- one error envelope ----------------------------------------------------


def test_validation_errors_use_the_shared_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": 123})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "name"]


def test_unknown_routes_use_the_shared_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_unhandled_errors_are_hidden_behind_a_generic_500(make_client) -> None:
    client = make_client()

    @client.app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text


def test_pool_timeout_becomes_503(make_client) -> None:
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError

    client = make_client()

    @client.app.get("/busy")
    def busy() -> None:
        raise PoolTimeoutError("pool exhausted")

    response = client.get("/busy")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_busy"
    assert response.headers["retry-after"] == "2"


# --- headers, request ids, body limits -----------------------------------


def test_security_headers_and_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    # COOP would cut the Google sign-in popup off from its opener.
    assert "cross-origin-opener-policy" not in response.headers
    assert len(response.headers["x-request-id"]) >= 16
    echoed = client.get("/api/v1/health", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers["x-request-id"] == "trace-123"


def test_hsts_is_sent_when_cookies_are_secure(make_client) -> None:
    client = make_client(
        app_environment="production",
        auth_cookie_secure=True,
        api_key_encryption_secret=_TEST_PROD_BYOK_KEY,
    )
    assert "max-age" in client.get("/api/v1/health").headers["strict-transport-security"]


def test_oversized_json_body_is_rejected_before_parsing(make_client) -> None:
    client = make_client(max_json_body_bytes=2048)
    _register_and_login(client)
    response = client.post(
        "/api/v1/projects",
        content=b'{"name": "' + b"a" * 10_000 + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_streamed_upload_beyond_the_limit_is_rejected(make_client) -> None:
    client = make_client(document_max_upload_bytes=1024)
    _register_and_login(client)

    def body():
        yield b"--b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pdf\"\r\n"
        yield b"Content-Type: application/pdf\r\n\r\n%PDF-1.4\n"
        for _ in range(64):
            yield b"0" * 65536
        yield b"\r\n--b--\r\n"

    response = client.post(
        "/api/v1/documents",
        content=body(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert response.status_code == 413


# --- CSRF / origin ---------------------------------------------------------


def test_unsafe_requests_without_origin_or_referer_are_refused(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "x"}, headers={"Origin": ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_required"


def test_referer_is_accepted_when_origin_is_missing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"name": "From referer"},
        headers={"Origin": "", "Referer": f"{FRONTEND_ORIGIN}/projects"},
    )
    assert response.status_code == 201


def test_foreign_origin_is_refused(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


# --- rate limiting & login hardening --------------------------------------


def test_login_is_rate_limited_per_ip(make_client) -> None:
    client = make_client(rate_limit_enabled=True, rate_limit_login_per_minute=3)
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 401
    limited = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1


def test_login_is_rate_limited_per_account(make_client) -> None:
    client = make_client(
        rate_limit_enabled=True,
        rate_limit_login_per_minute=100,
        rate_limit_login_per_account_per_hour=2,
    )
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"email": "Target@example.com", "password": "x"})
    assert client.post("/api/v1/auth/login", json={"email": "target@example.com", "password": "x"}).status_code == 429
    assert client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "x"}).status_code == 401


def test_registration_is_rate_limited(make_client) -> None:
    client = make_client(rate_limit_enabled=True, rate_limit_register_per_hour=1)
    assert client.post("/api/v1/auth/register", json={"name": "a", "email": "a1@example.com", "password": "long-password-123"}).status_code == 201
    assert client.post("/api/v1/auth/register", json={"name": "a", "email": "a2@example.com", "password": "long-password-123"}).status_code == 429


def test_research_queries_are_rate_limited_per_user(make_client) -> None:
    client = make_client(rate_limit_enabled=True, rate_limit_query_per_minute=1)
    _register_and_login(client)
    first = client.post("/api/v1/research/retrieve", json={"query": "anything"})
    assert first.status_code == 503  # SQLite has no retrieval backend
    assert client.post("/api/v1/research/retrieve", json={"query": "anything"}).status_code == 429


def test_unknown_email_still_pays_for_password_hashing(client: TestClient, monkeypatch) -> None:
    calls = []
    real_hasher = auth_sessions.password_hasher

    class CountingHasher:
        def verify(self, hash_value, password):
            calls.append(hash_value)
            return real_hasher.verify(hash_value, password)

    monkeypatch.setattr(auth_sessions, "password_hasher", CountingHasher())
    response = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "whatever-123"})
    assert response.status_code == 401
    assert calls == [auth_sessions._TIMING_EQUALIZER_HASH]


def test_login_fields_have_length_limits(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "p" * 2000})
    assert response.status_code == 422


@pytest.mark.parametrize("password", ["aaaaaaaa", "password123", "12121212"])
def test_trivial_passwords_are_rejected(client: TestClient, password: str) -> None:
    response = client.post("/api/v1/auth/register", json={"name": "W", "email": "weak@example.com", "password": password})
    assert response.status_code == 422


# --- sessions ----------------------------------------------------------------


def test_sessions_per_user_are_capped(make_client, tmp_path: Path) -> None:
    client = make_client(auth_max_sessions_per_user=3)
    _register_and_login(client)
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "long-password-123"})
    with client.app.state.db_session_factory() as session:
        assert session.query(AuthSession).count() == 3
    assert client.get("/api/v1/auth/me").status_code == 200


def test_logout_all_revokes_every_session(client: TestClient, db_session_factory: sessionmaker[Session]) -> None:
    other = TestClient(client.app, headers=FRONTEND_HEADERS)
    other.post("/api/v1/auth/login", json={"email": "researcher@example.com", "password": "test-password-123"})
    assert other.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout-all").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401
    with db_session_factory() as session:
        assert session.query(AuthSession).count() == 0


def test_expired_sessions_and_oauth_states_are_purged(client: TestClient, db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory() as session:
        user = session.scalar(select(User))
        session.add(AuthSession(token_hash="e" * 64, user_id=user.id, expires_at=utc_now() - timedelta(days=1)))
        session.add(OAuthState(state_hash="s" * 64, expires_at=utc_now() - timedelta(minutes=1)))
        session.commit()
        assert auth_sessions.purge_expired(session) == (1, 1)
        assert session.query(AuthSession).count() == 1  # the live login session


# --- readiness ---------------------------------------------------------------


def test_readiness_reports_dependencies(client: TestClient, monkeypatch) -> None:
    from app.api.routes import health

    request = httpx.Request("GET", "http://ollama/api/tags")
    monkeypatch.setattr(
        health.httpx,
        "get",
        lambda *a, **k: httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]}, request=request),
    )
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(health.httpx, "get", down)
    not_ready = client.get("/api/v1/health/ready")
    assert not_ready.status_code == 503
    checks = {item["name"]: item for item in not_ready.json()["checks"]}
    assert checks["database"]["ok"] is True
    assert checks["ollama"]["ok"] is False


def test_liveness_alias(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json()["status"] == "ok"
