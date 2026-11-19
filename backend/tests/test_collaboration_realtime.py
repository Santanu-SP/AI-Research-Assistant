"""Comprehensive tests for multi-user collaboration, RBAC, concurrency, and WebSocket sync."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.domain.documents import DocumentStatus, DocumentType
from app.models.document import Document, DocumentChunk
from app.models.usage import ModelUsageDaily
from app.models.report import ReportFollowup
from app.schemas.reports import ResearchReportCreate
from app.services.rag import query as rag_query_service
from app.services.rag import retrieval as rag_retrieval
from app.services.research import reports as report_service


def _default_test_phrase() -> str:
    return ("test-" * 3) + "phrase"


def _make_client(app: FastAPI) -> TestClient:
    origins = getattr(app.state.settings, "cors_origins", None) or ["http://localhost:5173"]
    return TestClient(app, headers={"Origin": origins[0]})


def _register_and_login(
    app: FastAPI,
    *,
    name: str,
    email: str,
    password: str | None = None,
) -> tuple[TestClient, dict]:
    secret_phrase = password or _default_test_phrase()
    client = _make_client(app)
    reg = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": secret_phrase},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": secret_phrase},
    )
    assert login.status_code == 200, login.text
    return client, reg.json()


def _receive_event(ws, expected_type: str, *, limit: int = 8) -> dict:
    seen: list[dict] = []
    for _ in range(limit):
        msg = ws.receive_json()
        seen.append(msg)
        if msg.get("type") == expected_type:
            return msg
    raise AssertionError(f"Expected WebSocket event {expected_type!r}, saw: {seen}")


def _receive_matching(ws, predicate, *, limit: int = 8) -> dict:
    seen: list[dict] = []
    for _ in range(limit):
        msg = ws.receive_json()
        seen.append(msg)
        if predicate(msg):
            return msg
    raise AssertionError(f"Condition never matched on WebSocket, saw: {seen}")


def _seed_completed_report(
    session: Session,
    owner_client: TestClient,
    *,
    project_id: str | None = None,
    title: str = "Shared Synthesis",
) -> tuple[UUID, UUID]:
    payload: dict[str, object] = {
        "question": "What does the shared evidence demonstrate?",
        "title": title,
    }
    if project_id is not None:
        payload["projectId"] = project_id
    created = owner_client.post("/api/v1/research", json=payload)
    assert created.status_code == 201, created.text
    research_id = UUID(created.json()["id"])

    source_id = uuid4()
    report_service.persist_report(
        session,
        research_id,
        ResearchReportCreate(
            title=title,
            summary="Shared baseline conclusion grounded in primary source [S1].",
            dossier_ref="SYNTHESIS MEMO · REF #COLLAB-001",
            reading_time_minutes=4,
            version=1,
            sources=[
                {
                    "id": source_id,
                    "number": 1,
                    "title": "Collaborative Evidence Study",
                    "publisher": "Journal of Collaboration",
                    "authors": ["A. Collaborator"],
                    "year": 2025,
                    "url": "https://example.test/collab-study",
                    "sourceType": "peer-reviewed",
                    "relevantExcerpt": "Controlled team runs reproduce findings [S1].",
                }
            ],
            sections=[
                {
                    "heading": "Findings",
                    "content": "Primary evidence supports collaboration [S1].",
                    "quote": "Controlled team runs reproduce findings.",
                    "position": 0,
                    "citations": [{"sourceId": source_id, "position": 0}],
                }
            ],
        ),
    )
    session.commit()
    return research_id, source_id


def test_alembic_0022_upgrade_and_downgrade_sqlite(tmp_path: Path, monkeypatch) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'collab_roundtrip.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(repo_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        try:
            insp = inspect(engine)
            tables = set(insp.get_table_names())
            assert {"project_members", "research_members", "collaboration_invites"}.issubset(tables)
            assert "version" in {c["name"] for c in insp.get_columns("research_projects")}
            assert "version" in {c["name"] for c in insp.get_columns("research")}
            assert "user_id" in {c["name"] for c in insp.get_columns("report_followups")}
        finally:
            engine.dispose()

        command.downgrade(cfg, "0021_report_followups")
        engine = create_engine(db_url)
        try:
            insp = inspect(engine)
            tables = set(insp.get_table_names())
            assert "project_members" not in tables
            assert "research_members" not in tables
            assert "collaboration_invites" not in tables
            assert "version" not in {c["name"] for c in insp.get_columns("research_projects")}
            assert "version" not in {c["name"] for c in insp.get_columns("research")}
            assert "user_id" not in {c["name"] for c in insp.get_columns("report_followups")}
        finally:
            engine.dispose()

        command.upgrade(cfg, "head")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()


def test_email_and_link_invites_preview_accept_limits_and_revoke(test_app: FastAPI) -> None:
    with (
        _register_and_login(test_app, name="Alice", email="alice-inv@example.com")[0] as alice,
        _register_and_login(test_app, name="Bob", email="bob-inv@example.com")[0] as bob,
        _register_and_login(test_app, name="Dave", email="dave-inv@example.com")[0] as dave,
        _register_and_login(test_app, name="Eve", email="eve-inv@example.com")[0] as eve,
    ):
        proj = alice.post(
            "/api/v1/projects",
            json={"name": "Invite Team Project", "description": "Testing invites"},
        ).json()
        pid = proj["id"]

        # Direct email invite for an already registered account (Bob) adds immediately.
        direct = alice.post(
            f"/api/v1/projects/{pid}/members",
            json={"email": "bob-inv@example.com", "role": "editor"},
        )
        assert direct.status_code == 201, direct.text
        assert direct.json()["memberAdded"] is True
        assert bob.get(f"/api/v1/projects/{pid}").json()["myRole"] == "editor"

        # Pending email invite for an unregistered email (Carol).
        pending = alice.post(
            f"/api/v1/projects/{pid}/members",
            json={"email": "carol-inv@example.com", "role": "viewer"},
        )
        assert pending.status_code == 201, pending.text
        assert pending.json()["memberAdded"] is False
        carol_token = pending.json()["token"]

        # Wrong logged-in user cannot accept an email-targeted invite.
        wrong_accept = dave.post(f"/api/v1/collaboration/invites/{carol_token}/accept")
        assert wrong_accept.status_code == 403
        assert wrong_accept.json()["error"]["code"] == "invite_email_mismatch"

        # Once Carol registers and logs in, preview and acceptance succeed.
        with _register_and_login(test_app, name="Carol", email="carol-inv@example.com")[0] as carol:
            preview = carol.get(f"/api/v1/collaboration/invites/{carol_token}")
            assert preview.status_code == 200
            assert preview.json()["resourceTitle"] == "Invite Team Project"
            assert preview.json()["role"] == "viewer"

            accepted = carol.post(f"/api/v1/collaboration/invites/{carol_token}/accept")
            assert accepted.status_code == 200
            assert accepted.json()["role"] == "viewer"
            assert carol.get(f"/api/v1/projects/{pid}").json()["myRole"] == "viewer"

        # Shareable link with maxUses=1 allows first user and blocks second user (410).
        one_time = alice.post(
            f"/api/v1/projects/{pid}/invites",
            json={"role": "editor", "maxUses": 1},
        )
        assert one_time.status_code == 201
        one_token = one_time.json()["token"]
        assert dave.post(f"/api/v1/collaboration/invites/{one_token}/accept").status_code == 200
        exhausted = eve.post(f"/api/v1/collaboration/invites/{one_token}/accept")
        assert exhausted.status_code == 410
        assert exhausted.json()["error"]["code"] == "invite_exhausted"

        # Revoked invite link returns 410 invite_revoked.
        rev_link = alice.post(f"/api/v1/projects/{pid}/invites", json={"role": "viewer"}).json()
        del_resp = alice.delete(f"/api/v1/projects/{pid}/invites/{rev_link['invite']['id']}")
        assert del_resp.status_code == 204
        revoked_use = eve.post(f"/api/v1/collaboration/invites/{rev_link['token']}/accept")
        assert revoked_use.status_code == 410
        assert revoked_use.json()["error"]["code"] == "invite_revoked"


def test_rbac_matrix_owner_editor_viewer_and_stranger(
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
) -> None:
    from tests.test_documents_api import PDF_MIME, make_pdf

    alice, alice_user = _register_and_login(test_app, name="Alice", email="alice-rbac@example.com")
    bob, bob_user = _register_and_login(test_app, name="Bob", email="bob-rbac@example.com")
    carol, _ = _register_and_login(test_app, name="Carol", email="carol-rbac@example.com")
    stranger, _ = _register_and_login(test_app, name="Stranger", email="stranger-rbac@example.com")

    with alice, bob, carol, stranger:
        proj = alice.post("/api/v1/projects", json={"name": "RBAC Project"}).json()
        pid = proj["id"]

        # Seed a completed research report inside the shared project.
        with db_session_factory() as session:
            research_id, _ = _seed_completed_report(session, alice, project_id=pid)

        assert alice.post(
            f"/api/v1/projects/{pid}/members",
            json={"email": "bob-rbac@example.com", "role": "editor"},
        ).status_code == 201
        assert alice.post(
            f"/api/v1/projects/{pid}/members",
            json={"email": "carol-rbac@example.com", "role": "viewer"},
        ).status_code == 201

        # Upload one doc as Alice so everyone with access can test reading it.
        doc = alice.post(
            f"/api/v1/projects/{pid}/documents",
            files={"file": ("rbac.pdf", make_pdf("RBAC content"), PDF_MIME)},
        )
        assert doc.status_code == 201, doc.text
        doc_id = doc.json()["id"]

        # Stranger receives 404 across project, document, research, report, members.
        assert stranger.get(f"/api/v1/projects/{pid}").status_code == 404
        assert stranger.get(f"/api/v1/documents/{doc_id}").status_code == 404
        assert stranger.get(f"/api/v1/research/{research_id}/report").status_code == 404
        assert stranger.get(f"/api/v1/projects/{pid}/members").status_code == 404

        # Viewer can read everything, but receives 403 on all mutations & AI executions.
        assert carol.get(f"/api/v1/projects/{pid}").status_code == 200
        assert carol.get(f"/api/v1/documents/{doc_id}").status_code == 200
        assert carol.get(f"/api/v1/research/{research_id}/report").status_code == 200
        assert carol.get(f"/api/v1/projects/{pid}/members").status_code == 200

        assert (
            carol.post(
                f"/api/v1/projects/{pid}/documents",
                files={"file": ("blocked.pdf", make_pdf("no"), PDF_MIME)},
            ).status_code
            == 403
        )
        assert (
            carol.post(
                "/api/v1/discovery/import",
                json={
                    "projectId": pid,
                    "items": [
                        {
                            "candidateId": "c1",
                            "provider": "openalex",
                            "trustTier": "peer-reviewed",
                            "sourceType": "openalex",
                            "contentLevel": "abstract",
                            "title": "Blocked Source",
                            "url": "https://example.test/paper",
                            "abstract": "Test",
                        }
                    ],
                },
            ).status_code
            == 403
        )
        assert carol.patch(f"/api/v1/projects/{pid}", json={"name": "Nope"}).status_code == 403
        assert carol.patch(f"/api/v1/research/{research_id}", json={"title": "Nope"}).status_code == 403
        assert (
            carol.post(
                "/api/v1/research/query",
                json={"query": "Can viewer run AI?", "projectId": pid},
            ).status_code
            == 403
        )
        assert carol.post(f"/api/v1/research/{research_id}/retry").status_code == 403
        assert (
            carol.post(
                f"/api/v1/research/{research_id}/followups",
                json={"question": "Can viewer ask followup?"},
            ).status_code
            == 403
        )
        assert carol.delete(f"/api/v1/projects/{pid}").status_code == 403
        assert (
            carol.post(
                f"/api/v1/projects/{pid}/members",
                json={"email": "x@example.com", "role": "viewer"},
            ).status_code
            == 403
        )

        # Editor can upload & edit metadata/research, but cannot archive, delete, or manage members.
        bob_doc = bob.post(
            f"/api/v1/projects/{pid}/documents",
            files={"file": ("bob.pdf", make_pdf("Bob contribution"), PDF_MIME)},
        )
        assert bob_doc.status_code == 201, bob_doc.text
        assert bob.patch(f"/api/v1/projects/{pid}", json={"name": "Team Project v2"}).status_code == 200
        assert bob.patch(
            f"/api/v1/research/{research_id}",
            json={"title": "Edited by Bob"},
        ).status_code == 200
        assert bob.delete(f"/api/v1/projects/{pid}").status_code == 403
        assert bob.delete(f"/api/v1/research/{research_id}").status_code == 403
        assert (
            bob.patch(
                f"/api/v1/projects/{pid}/members/{alice_user['id']}",
                json={"role": "viewer"},
            ).status_code
            == 403
        )

        # Owner can update collaborator role and remove a member.
        role_change = alice.patch(
            f"/api/v1/projects/{pid}/members/{bob_user['id']}",
            json={"role": "viewer"},
        )
        assert role_change.status_code == 200
        assert role_change.json()["role"] == "viewer"
        assert bob.patch(f"/api/v1/projects/{pid}", json={"name": "Now blocked"}).status_code == 403

        assert alice.delete(f"/api/v1/projects/{pid}/members/{bob_user['id']}").status_code == 204
        assert bob.get(f"/api/v1/projects/{pid}").status_code == 404


def test_shared_project_files_dedup_and_cross_user_rag_retrieval(
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
) -> None:
    from tests.test_documents_api import PDF_MIME, make_pdf

    alice, alice_user = _register_and_login(test_app, name="Alice", email="alice-rag@example.com")
    bob, bob_user = _register_and_login(test_app, name="Bob", email="bob-rag@example.com")
    stranger, stranger_user = _register_and_login(
        test_app, name="Stranger", email="stranger-rag@example.com"
    )

    with alice, bob, stranger:
        pid = alice.post("/api/v1/projects", json={"name": "RAG Share"}).json()["id"]
        assert (
            alice.post(
                f"/api/v1/projects/{pid}/members",
                json={"email": "bob-rag@example.com", "role": "editor"},
            ).status_code
            == 201
        )

        pdf_bytes = make_pdf("Xylophone quantum spectroscopy results confirm the hypothesis.")
        doc_a = alice.post(
            f"/api/v1/projects/{pid}/documents",
            files={"file": ("shared-paper.pdf", pdf_bytes, PDF_MIME)},
        )
        assert doc_a.status_code == 201, doc_a.text
        doc_id = doc_a.json()["id"]

        # Bob lists the shared project's documents and reads Alice's PDF.
        bob_docs = bob.get("/api/v1/documents", params={"projectId": pid})
        assert bob_docs.status_code == 200
        assert [item["id"] for item in bob_docs.json()["items"]] == [doc_id]

        # Bob uploading identical bytes in the same shared project hits project-wide
        # deduplication instead of creating duplicate storage/chunks.
        doc_b = bob.post(
            f"/api/v1/projects/{pid}/documents",
            files={"file": ("shared-paper.pdf", pdf_bytes, PDF_MIME)},
        )
        assert doc_b.status_code == 409, doc_b.text
        assert doc_b.json()["error"]["code"] == "duplicate_document"
        assert doc_b.json()["error"]["details"]["documentId"] == doc_id

        # Ensure an indexed chunk exists for keyword + vector SQLite retrieval test.
        vec = [0.01] * 1024
        vec[0] = 0.99
        fake_embeddings = SimpleNamespace(embed_query=lambda _q: vec)
        sqlite_settings = Settings(allow_sqlite_retrieval_fallback=True)
        with db_session_factory() as session:
            doc_row = session.get(Document, UUID(doc_id))
            assert doc_row is not None
            doc_row.status = DocumentStatus.INDEXED
            if (
                session.scalar(
                    select(DocumentChunk.id).where(DocumentChunk.document_id == doc_row.id)
                )
                is None
            ):
                session.add(
                    DocumentChunk(
                        id=uuid4(),
                        document_id=doc_row.id,
                        node_id="shared-node-1",
                        chunk_index=0,
                        page=1,
                        text="Xylophone quantum spectroscopy demonstrates clear spectral peaks.",
                        embedding=vec,
                    )
                )
            else:
                chunk_row = session.scalars(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc_row.id)
                ).first()
                assert chunk_row is not None
                chunk_row.embedding = vec
            session.commit()

            bob_hits = rag_retrieval.retrieve(
                session,
                UUID(bob_user["id"]),
                "xylophone quantum spectroscopy",
                sqlite_settings,
                embeddings=fake_embeddings,
                project_id=UUID(pid),
            )
            assert len(bob_hits) >= 1
            assert bob_hits[0].document_id == UUID(doc_id)

            # Stranger gets 404 when scoping to the shared project, and 0 hits unscoped.
            with pytest.raises(Exception):
                rag_retrieval.retrieve(
                    session,
                    UUID(stranger_user["id"]),
                    "xylophone quantum spectroscopy",
                    sqlite_settings,
                    embeddings=fake_embeddings,
                    project_id=UUID(pid),
                )
            unscoped_stranger = rag_retrieval.retrieve(
                session,
                UUID(stranger_user["id"]),
                "xylophone quantum spectroscopy",
                sqlite_settings,
                embeddings=fake_embeddings,
            )
            assert unscoped_stranger == []


def test_simultaneous_followups_author_attribution_and_per_user_quota(
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    alice, alice_user = _register_and_login(test_app, name="Alice Author", email="alice-fu@example.com")
    bob, bob_user = _register_and_login(test_app, name="Bob Author", email="bob-fu@example.com")

    class _FakeGenerator:
        def __init__(self) -> None:
            self.last_response = SimpleNamespace(
                provider="openrouter",
                model="fake-collab-model",
                used_byok=False,
                usage=SimpleNamespace(prompt_tokens=15, completion_tokens=25, total_tokens=40),
            )

        def generate(self, question: str, _evidence, **_kwargs) -> str:
            return f"Grounded answer to ({question}) based on team evidence [S1]."

    monkeypatch.setattr(rag_query_service, "generation_service_for", lambda _s: _FakeGenerator())
    monkeypatch.setattr(rag_query_service.retrieval, "retrieve", lambda *args, **kwargs: [])
    monkeypatch.setattr(rag_query_service, "evidence_is_sufficient", lambda *args, **kwargs: True)

    with alice, bob:
        with db_session_factory() as session:
            research_id, _ = _seed_completed_report(session, alice, title="Concurrent QA")

        assert (
            alice.post(
                f"/api/v1/research/{research_id}/members",
                json={"email": "bob-fu@example.com", "role": "editor"},
            ).status_code
            == 201
        )

        # Fire concurrent follow-ups from both collaborators.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_alice = pool.submit(
                alice.post,
                f"/api/v1/research/{research_id}/followups",
                json={"question": "Alice question on [S1]?"},
            )
            f_bob = pool.submit(
                bob.post,
                f"/api/v1/research/{research_id}/followups",
                json={"question": "Bob question on [S1]?"},
            )
            resp_alice = f_alice.result()
            resp_bob = f_bob.result()

        assert resp_alice.status_code == 201, resp_alice.text
        assert resp_bob.status_code == 201, resp_bob.text
        body_a = resp_alice.json()["followup"]
        body_b = resp_bob.json()["followup"]

        assert {body_a["position"], body_b["position"]} == {0, 1}
        assert body_a["authorName"] == "Alice Author"
        assert body_b["authorName"] == "Bob Author"

        # Check database persistence + independent per-user usage attribution.
        with db_session_factory() as session:
            saved = session.scalars(
                select(ReportFollowup).order_by(ReportFollowup.position.asc())
            ).all()
            assert len(saved) == 2
            logs = session.scalars(select(ModelUsageDaily)).all()
            log_users = {str(item.user_id) for item in logs}
            assert log_users == {alice_user["id"], bob_user["id"]}


def test_optimistic_locking_returns_409_version_conflict(
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
) -> None:
    alice, _ = _register_and_login(test_app, name="Alice Lock", email="alice-lock@example.com")
    bob, _ = _register_and_login(test_app, name="Bob Lock", email="bob-lock@example.com")

    with alice, bob:
        proj = alice.post("/api/v1/projects", json={"name": "Lock Project"}).json()
        pid = proj["id"]
        assert proj["version"] == 1

        assert (
            alice.post(
                f"/api/v1/projects/{pid}/members",
                json={"email": "bob-lock@example.com", "role": "editor"},
            ).status_code
            == 201
        )

        # Alice edits with version=1 -> succeeds and bumps version to 2.
        a_patch = alice.patch(
            f"/api/v1/projects/{pid}",
            json={"name": "Alice Updated Name", "version": 1},
        )
        assert a_patch.status_code == 200
        assert a_patch.json()["version"] == 2

        # Bob edits with stale version=1 -> 409 version_conflict.
        b_patch = bob.patch(
            f"/api/v1/projects/{pid}",
            json={"name": "Bob Stale Name", "version": 1},
        )
        assert b_patch.status_code == 409
        assert b_patch.json()["error"]["code"] == "version_conflict"

        # Same optimistic lock check on Research metadata updates.
        with db_session_factory() as session:
            research_id, _ = _seed_completed_report(session, alice, project_id=pid)

        r1 = alice.patch(
            f"/api/v1/research/{research_id}",
            json={"title": "Research v2", "version": 1},
        )
        assert r1.status_code == 200
        assert r1.json()["version"] == 2

        r2 = bob.patch(
            f"/api/v1/research/{research_id}",
            json={"title": "Research stale", "version": 1},
        )
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "version_conflict"


def _issue_user_headers(
    client: TestClient,
    *,
    name: str,
    email: str,
    origin: str,
) -> tuple[dict[str, str], dict]:
    secret_phrase = _default_test_phrase()
    client.cookies.clear()
    reg = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": secret_phrase},
        headers={"Origin": origin},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": secret_phrase},
        headers={"Origin": origin},
    )
    assert login.status_code == 200, login.text
    cookie_header = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    client.cookies.clear()
    return {"Origin": origin, "Cookie": cookie_header}, reg.json()


def test_websocket_auth_presence_activity_and_realtime_broadcasts(
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    from tests.test_documents_api import PDF_MIME, make_pdf

    class _FakeGenerator:
        def __init__(self) -> None:
            self.last_response = SimpleNamespace(
                provider="ollama",
                model="qwen3:8b",
                used_byok=False,
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=12, total_tokens=22),
            )

        def generate(self, question: str, _evidence, **_kwargs) -> str:
            return f"Realtime answer ({question}) [S1]."

    monkeypatch.setattr(rag_query_service, "generation_service_for", lambda _s: _FakeGenerator())
    monkeypatch.setattr(rag_query_service.retrieval, "retrieve", lambda *args, **kwargs: [])
    monkeypatch.setattr(rag_query_service, "evidence_is_sufficient", lambda *args, **kwargs: True)

    origins = getattr(test_app.state.settings, "cors_origins", None) or ["http://localhost:5173"]
    origin = origins[0]
    anon_headers = {"Origin": origin}

    with _make_client(test_app) as client:
        alice_headers, alice_user = _issue_user_headers(
            client, name="Alice WS", email="alice-ws@example.com", origin=origin
        )
        bob_headers, bob_user = _issue_user_headers(
            client, name="Bob WS", email="bob-ws@example.com", origin=origin
        )
        stranger_headers, _ = _issue_user_headers(
            client, name="Stranger WS", email="stranger-ws@example.com", origin=origin
        )

        proj = client.post(
            "/api/v1/projects",
            json={"name": "Realtime WS Project"},
            headers=alice_headers,
        ).json()
        pid = proj["id"]
        assert (
            client.post(
                f"/api/v1/projects/{pid}/members",
                json={"email": "bob-ws@example.com", "role": "editor"},
                headers=alice_headers,
            ).status_code
            == 201
        )
        res_create = client.post(
            "/api/v1/research",
            json={"question": "What does WS evidence show?", "title": "WS Research", "projectId": pid},
            headers=alice_headers,
        )
        assert res_create.status_code == 201, res_create.text
        research_id = UUID(res_create.json()["id"])
        source_id = uuid4()
        with db_session_factory() as session:
            report_service.persist_report(
                session,
                research_id,
                ResearchReportCreate(
                    title="WS Research",
                    summary="Baseline [S1].",
                    dossier_ref="REF #WS",
                    reading_time_minutes=2,
                    version=1,
                    sources=[
                        {
                            "id": source_id,
                            "number": 1,
                            "title": "WS Study",
                            "sourceType": "peer-reviewed",
                            "relevantExcerpt": "Realtime proof [S1].",
                        }
                    ],
                    sections=[
                        {
                            "heading": "Summary",
                            "content": "WS findings [S1].",
                            "position": 0,
                            "citations": [{"sourceId": source_id, "position": 0}],
                        }
                    ],
                ),
            )
            session.commit()

        # Unauthenticated WebSocket connection closes with 4401.
        with pytest.raises(WebSocketDisconnect) as unauth_exc:
            with client.websocket_connect(f"/api/v1/ws/projects/{pid}", headers=anon_headers):
                pass
        assert unauth_exc.value.code == 4401

        # Stranger WebSocket connection closes with 4404.
        with pytest.raises(WebSocketDisconnect) as stranger_exc:
            with client.websocket_connect(f"/api/v1/ws/projects/{pid}", headers=stranger_headers):
                pass
        assert stranger_exc.value.code == 4404

        # Live project WebSocket: presence, activity updates, document.added & project.updated.
        with client.websocket_connect(f"/api/v1/ws/projects/{pid}", headers=alice_headers) as ws_a:
            _receive_event(ws_a, "presence.sync")
            with client.websocket_connect(f"/api/v1/ws/projects/{pid}", headers=bob_headers) as ws_b:
                bob_sync = _receive_event(ws_b, "presence.sync")
                assert {m["userId"] for m in bob_sync["payload"]["members"]} == {
                    alice_user["id"],
                    bob_user["id"],
                }
                _receive_matching(
                    ws_a,
                    lambda msg: msg.get("type") == "presence.sync"
                    and len(msg.get("payload", {}).get("members", [])) == 2,
                )

                # Activity update broadcasts immediately to Bob.
                ws_a.send_json({"type": "activity", "activity": "uploading"})
                activity_sync = _receive_matching(
                    ws_b,
                    lambda msg: msg.get("type") == "presence.sync"
                    and any(
                        m["userId"] == alice_user["id"] and m["activity"] == "uploading"
                        for m in msg.get("payload", {}).get("members", [])
                    ),
                )
                assert activity_sync["type"] == "presence.sync"

                # Uploading a file pushes document.added in real time.
                up = client.post(
                    f"/api/v1/projects/{pid}/documents",
                    files={"file": ("live.pdf", make_pdf("Live upload"), PDF_MIME)},
                    headers=alice_headers,
                )
                assert up.status_code == 201
                doc_event = _receive_event(ws_b, "document.added")
                assert doc_event["payload"]["documentId"] == up.json()["id"]

                # Project metadata rename pushes project.updated in real time.
                patch_resp = client.patch(
                    f"/api/v1/projects/{pid}",
                    json={"name": "Realtime Renamed Project"},
                    headers=alice_headers,
                )
                assert patch_resp.status_code == 200
                proj_event = _receive_event(ws_b, "project.updated")
                assert proj_event["payload"]["name"] == "Realtime Renamed Project"

        # Live research WebSocket: Bob posts a follow-up, Alice receives followup.created.
        with client.websocket_connect(
            f"/api/v1/ws/research/{research_id}", headers=alice_headers
        ) as ws_res_a:
            _receive_event(ws_res_a, "presence.sync")
            fu = client.post(
                f"/api/v1/research/{research_id}/followups",
                json={"question": "Live WS followup on [S1]?"},
                headers=bob_headers,
            )
            assert fu.status_code == 201, fu.text
            fu_event = _receive_event(ws_res_a, "followup.created")
            assert fu_event["payload"]["followup"]["authorName"] == "Bob WS"
            assert fu_event["payload"]["followup"]["id"] == fu.json()["followup"]["id"]
