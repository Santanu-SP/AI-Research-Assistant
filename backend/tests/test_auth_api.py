from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import timedelta
from uuid import UUID
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.models.user import AuthSession, User


def test_register_login_me_logout_and_protected_routes(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    client = anonymous_client
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/research").status_code == 401

    payload = {"name": "Alice", "email": "ALICE@example.com", "password": "long-password-123"}
    created = client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 201
    assert created.json()["email"] == "alice@example.com"
    assert "password" not in created.json()
    with db_session_factory() as session:
        user = session.get(User, UUID(created.json()["id"]))
        assert user is not None
        assert user.password_hash != payload["password"]
        assert user.password_hash.startswith("$argon2")
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": payload["email"], "password": "wrong"}).status_code == 401

    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["name"] == "Alice"
    assert client.get("/api/v1/documents").status_code == 200
    assert client.get("/api/v1/research").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    with db_session_factory() as session:
        assert session.query(AuthSession).count() == 0


def test_expired_session_is_rejected(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    client = anonymous_client
    client.post("/api/v1/auth/register", json={
        "name": "Expired", "email": "expired@example.com", "password": "long-password-123",
    })
    client.post("/api/v1/auth/login", json={
        "email": "expired@example.com", "password": "long-password-123",
    })
    with db_session_factory() as session:
        auth_session = session.query(AuthSession).one()
        auth_session.expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/documents").status_code == 401


def test_documents_and_research_are_isolated_by_owner(anonymous_client: TestClient) -> None:
    client = anonymous_client
    for name in ("Alice", "Bob"):
        assert client.post("/api/v1/auth/register", json={
            "name": name, "email": f"{name.lower()}@example.com", "password": "long-password-123",
        }).status_code == 201
    assert client.post("/api/v1/auth/login", json={
        "email": "alice@example.com", "password": "long-password-123",
    }).status_code == 200
    research = client.post("/api/v1/research", json={"question": "Alice's question?"})
    assert research.status_code == 201
    research_id = research.json()["id"]
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(72, 760, "A research paper with useful extractable text.")
    pdf.save()
    uploaded = client.post("/api/v1/documents", files={
        "file": ("alice.pdf", output.getvalue(), "application/pdf"),
    })
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    served = client.get(f"/api/v1/documents/{document_id}/file")
    assert served.status_code == 200
    assert served.headers["content-disposition"].startswith("inline")
    assert served.headers["cache-control"] == "private, no-store"
    assert served.headers["x-content-type-options"] == "nosniff"
    # The PDF viewer must not be blocked by the API's default-src 'none'.
    assert served.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/login", json={
        "email": "bob@example.com", "password": "long-password-123",
    }).status_code == 200
    assert client.get("/api/v1/research").json()["total"] == 0
    assert client.get("/api/v1/documents").json()["total"] == 0
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{document_id}/file").status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.get(f"/api/v1/research/{research_id}").status_code == 404
    assert client.delete(f"/api/v1/research/{research_id}").status_code == 404


def test_inactivity_session_slides_on_visit_and_expires_after_idle_days(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    client = anonymous_client
    settings = client.app.state.settings
    assert client.post("/api/v1/auth/register", json={
        "name": "Idle User", "email": "idle@example.com", "password": "long-password-123",
    }).status_code == 201
    assert client.post("/api/v1/auth/login", json={
        "email": "idle@example.com", "password": "long-password-123",
    }).status_code == 200

    with db_session_factory() as session:
        auth_session = session.query(AuthSession).one()
        initial_delta = auth_session.expires_at - auth_session.created_at
        expected_days = min(settings.auth_session_days, settings.auth_inactivity_days)
        assert timedelta(days=expected_days, seconds=-5) <= initial_delta <= timedelta(days=expected_days, seconds=5)

        # Simulate a returning visit 1 day later: sliding window should extend expires_at.
        stale_expires = auth_session.expires_at - timedelta(days=1)
        auth_session.expires_at = stale_expires
        session.commit()

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "idle@example.com"
    with db_session_factory() as session:
        refreshed = session.query(AuthSession).one()
        assert refreshed.expires_at > stale_expires

        # Simulate user staying away longer than auth_inactivity_days (created_at still < 7 days).
        refreshed.expires_at = utc_now() - timedelta(minutes=1)
        session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401
    with db_session_factory() as session:
        assert session.query(AuthSession).count() == 0


def test_hard_session_ceiling_expires_even_if_recently_active(
    anonymous_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    client = anonymous_client
    settings = client.app.state.settings
    assert client.post("/api/v1/auth/register", json={
        "name": "Aged User", "email": "aged@example.com", "password": "long-password-123",
    }).status_code == 201
    assert client.post("/api/v1/auth/login", json={
        "email": "aged@example.com", "password": "long-password-123",
    }).status_code == 200

    with db_session_factory() as session:
        auth_session = session.query(AuthSession).one()
        auth_session.created_at = utc_now() - timedelta(days=settings.auth_session_days, seconds=10)
        auth_session.expires_at = utc_now() + timedelta(days=1)
        session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401
    with db_session_factory() as session:
        assert session.query(AuthSession).count() == 0
