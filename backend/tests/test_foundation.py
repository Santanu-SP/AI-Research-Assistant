from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now


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


def test_utc_now_is_timezone_aware() -> None:
    timestamp = utc_now()

    assert timestamp.utcoffset() is not None
