from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.main import create_app


def test_application_starts_and_exposes_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AI Research Assistant API"


def test_database_session_can_execute_query(db_session: Session) -> None:
    assert db_session.scalar(text("SELECT 1")) == 1


def test_cors_allows_configured_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_does_not_allow_unconfigured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_development_cors_allows_private_lan_origin() -> None:
    settings = Settings(app_environment="development")
    app = create_app(settings)
    with TestClient(app) as test_client:
        response = test_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://10.110.156.117:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://10.110.156.117:3000"


def test_application_error_uses_shared_response_contract(
    client: TestClient,
) -> None:
    @client.app.get("/test-error")
    def raise_test_error() -> None:
        raise AppError("Expected failure", status_code=409, code="test_conflict")

    response = client.get("/test-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "test_conflict",
            "message": "Expected failure",
        }
    }


def test_settings_accept_future_postgresql_url() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:pass@db/app")

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_builds_a_secure_supabase_url_from_connection_fields() -> None:
    settings = Settings(
        SUPABASE_DB_USER="postgres.example",
        SUPABASE_DB_PASSWORD="reserved@characters?are/safe",
        SUPABASE_DB_HOST="aws-0-example.pooler.supabase.com",
        SUPABASE_DB_PORT=5432,
        SUPABASE_DB_NAME="postgres",
    )

    url = make_url(settings.database_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "postgres.example"
    assert url.password == "reserved@characters?are/safe"
    assert url.host == "aws-0-example.pooler.supabase.com"
    assert url.port == 5432
    assert url.database == "postgres"
    assert url.query["sslmode"] == "require"


def test_utc_now_is_timezone_aware() -> None:
    timestamp = utc_now()

    assert timestamp.utcoffset() is not None
