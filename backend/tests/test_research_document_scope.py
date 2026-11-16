"""A research run reads only the documents attached to it."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.document import Document
from app.models.research import Research
from app.services.rag import query as rag_service
from conftest import FRONTEND_HEADERS
from test_architecture_upgrade import DeterministicEmbeddingService, KeywordAwareReranker
from test_documents_api import make_pdf, upload_document
from test_rag_api import candidates


class RecordingGenerator:
    def __init__(self) -> None:
        self.evidence_documents: list[set[UUID]] = []

    def generate(self, question, evidence, **_kwargs):
        self.evidence_documents.append({item.document_id for item in evidence})
        return "Quantum annealing lowers energy barriers [S1]."


def _real_retrieval(client: TestClient, monkeypatch) -> RecordingGenerator:
    """SQLite retrieval over real uploaded chunks, with a fake model."""
    settings = client.app.state.settings
    settings.embedding_enabled = True
    settings.allow_sqlite_retrieval_fallback = True
    embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda _s: KeywordAwareReranker())
    generator = RecordingGenerator()
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)
    return generator


def _upload(client: TestClient, name: str, text: str, project_id: str | None = None) -> str:
    files = {"file": (name, make_pdf(text), "application/pdf")}
    if project_id:
        response = client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    else:
        response = upload_document(client, filename=name, content=make_pdf(text))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _capture_scope(monkeypatch) -> list[tuple[UUID | None, list[UUID] | None]]:
    scopes: list[tuple[UUID | None, list[UUID] | None]] = []

    def fake_retrieve(session, user_id, query, settings, *, project_id=None, document_ids=None):
        scopes.append((project_id, document_ids))
        return candidates()

    monkeypatch.setattr(rag_service.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda _s: KeywordAwareReranker())
    generator = RecordingGenerator()
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)
    return scopes


QUESTION = "What lowers energy barriers in quantum annealing?"


def test_new_research_reads_only_the_attached_document(client: TestClient, monkeypatch) -> None:
    generator = _real_retrieval(client, monkeypatch)
    picked = _upload(client, "picked.pdf", "Quantum annealing lowers energy barriers in spin glasses.")
    other = _upload(client, "other.pdf", "Quantum annealing lowers energy barriers on other hardware.")

    response = client.post(
        "/api/v1/research/query", json={"query": QUESTION, "documentIds": [picked]}
    )
    assert response.status_code == 201, response.text
    assert generator.evidence_documents == [{UUID(picked)}]
    assert {c["documentId"] for c in response.json()["citations"]} == {picked}

    research = client.get(f"/api/v1/research/{response.json()['researchId']}").json()
    assert research["documentsScoped"] is True
    assert research["documentIds"] == [picked]

    # The same question over both files reads both.
    both = client.post(
        "/api/v1/research/query", json={"query": QUESTION, "documentIds": [picked, other]}
    )
    assert both.status_code == 201, both.text
    assert generator.evidence_documents[-1] == {UUID(picked), UUID(other)}


def test_progress_counts_only_attached_documents(client: TestClient, monkeypatch) -> None:
    _capture_scope(monkeypatch)
    picked = _upload(client, "a.pdf", "First document.")
    _upload(client, "b.pdf", "Second document.")
    _upload(client, "c.pdf", "Third document.")
    queued = client.post("/api/v1/research/jobs", json={"query": "Anything?", "documentIds": [picked]})
    progress = client.get(f"/api/v1/research/{queued.json()['id']}/status").json()
    assert progress["documentsReady"] == 1


def test_research_outside_a_project_needs_a_document(client: TestClient, monkeypatch) -> None:
    _capture_scope(monkeypatch)
    for path in ("/api/v1/research/query", "/api/v1/research/jobs"):
        response = client.post(path, json={"query": "Anything?", "documentIds": []})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "research_documents_required"
    assert client.get("/api/v1/research").json()["total"] == 0


def test_documents_of_another_user_or_unknown_ids_are_not_found(
    client: TestClient, test_app, monkeypatch
) -> None:
    _capture_scope(monkeypatch)
    with TestClient(test_app, headers=FRONTEND_HEADERS) as other_client:
        other_client.post("/api/v1/auth/register", json={
            "name": "Other", "email": "other@example.com", "password": "test-password-123",
        })
        other_client.post("/api/v1/auth/login", json={
            "email": "other@example.com", "password": "test-password-123",
        })
        foreign = _upload(other_client, "theirs.pdf", "Someone else's notes.")
    # The other client's login replaced the cookie jar entry; log back in.
    client.post("/api/v1/auth/login", json={
        "email": "researcher@example.com", "password": "test-password-123",
    })
    mine = _upload(client, "mine.pdf", "My notes.")

    for ids in ([foreign], [mine, foreign], [str(uuid4())]):
        response = client.post("/api/v1/research/jobs", json={"query": "Anything?", "documentIds": ids})
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "document_not_found"
    assert client.get("/api/v1/research").json()["total"] == 0


def test_project_research_uses_the_project_or_its_own_documents(
    client: TestClient, monkeypatch
) -> None:
    scopes = _capture_scope(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Spin glasses"}).json()
    in_project = _upload(client, "p.pdf", "Project paper.", project_id=project["id"])
    outside = _upload(client, "o.pdf", "Library paper.")

    whole = client.post("/api/v1/research/query", json={"query": "Anything?", "projectId": project["id"]})
    assert whole.status_code == 201, whole.text
    assert scopes[-1] == (UUID(project["id"]), None)

    picked = client.post(
        "/api/v1/research/query",
        json={"query": "Anything else?", "projectId": project["id"], "documentIds": [in_project]},
    )
    assert picked.status_code == 201, picked.text
    assert scopes[-1] == (UUID(project["id"]), [UUID(in_project)])

    wrong = client.post(
        "/api/v1/research/query",
        json={"query": "Another one?", "projectId": project["id"], "documentIds": [outside]},
    )
    assert wrong.status_code == 404
    assert wrong.json()["error"]["code"] == "document_not_found"


def test_repeat_submit_is_only_a_duplicate_for_the_same_documents(
    client: TestClient, monkeypatch
) -> None:
    _capture_scope(monkeypatch)
    first_doc = _upload(client, "a.pdf", "First.")
    second_doc = _upload(client, "b.pdf", "Second.")
    payload = {"query": "What does it say?", "documentIds": [first_doc]}
    first = client.post("/api/v1/research/jobs", json=payload).json()
    again = client.post("/api/v1/research/jobs", json=payload).json()
    assert again["id"] == first["id"]

    other = client.post(
        "/api/v1/research/jobs", json={**payload, "documentIds": [second_doc]}
    ).json()
    assert other["id"] != first["id"]
    blocked = client.post("/api/v1/research/query", json={**payload, "documentIds": [second_doc]})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["researchId"] == other["id"]


def test_retry_keeps_the_attached_documents(client: TestClient, monkeypatch) -> None:
    scopes = _capture_scope(monkeypatch)
    picked = _upload(client, "a.pdf", "First.")
    _upload(client, "b.pdf", "Second.")

    def model_down(question, evidence, **_kwargs):
        raise AppError("down", status_code=503, code="generation_unavailable")

    generator = RecordingGenerator()
    generator.generate = model_down
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)
    queued = client.post("/api/v1/research/jobs", json={"query": "Anything?", "documentIds": [picked]})
    client.app.state.job_worker.run_until_empty()
    research_id = queued.json()["id"]
    assert client.get(f"/api/v1/research/{research_id}/status").json()["status"] == "failed"

    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: RecordingGenerator())
    retried = client.post(
        f"/api/v1/research/{research_id}/retry", json={"query": "Anything at all?", "researchDepth": "quick"}
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["documentIds"] == [picked]
    client.app.state.job_worker.run_until_empty()
    assert scopes == [(None, [UUID(picked)]), (None, [UUID(picked)])]


def test_older_research_without_attachments_still_reads_all_documents(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    scopes = _capture_scope(monkeypatch)
    _upload(client, "a.pdf", "First.")
    response = client.post("/api/v1/research/jobs", json={"query": "Old style question?"})
    assert response.status_code == 202, response.text
    record = db_session.get(Research, UUID(response.json()["id"]))
    assert record.documents_scoped is False and record.document_ids == []
    client.app.state.job_worker.run_until_empty()
    assert scopes == [(None, None)]


def test_deleting_the_attached_document_does_not_widen_the_search(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    generator = _real_retrieval(client, monkeypatch)
    picked = _upload(client, "picked.pdf", "Quantum annealing lowers energy barriers in spin glasses.")
    _upload(client, "other.pdf", "Quantum annealing lowers energy barriers on other hardware.")
    queued = client.post("/api/v1/research/jobs", json={"query": QUESTION, "documentIds": [picked]})
    assert client.delete(f"/api/v1/documents/{picked}").status_code == 204
    assert db_session.get(Document, UUID(picked)) is None
    client.app.state.job_worker.run_until_empty()
    # Nothing left to read, so the model was never asked.
    assert generator.evidence_documents == []
    research = client.get(f"/api/v1/research/{queued.json()['id']}").json()
    assert research["documentsScoped"] is True and research["documentIds"] == []


def test_alembic_0017_upgrade_and_downgrade_sqlite(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'scope_roundtrip.db'}"
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
            assert "research_documents" in insp.get_table_names()
            assert "documents_scoped" in {c["name"] for c in insp.get_columns("research")}
        finally:
            engine.dispose()
        command.downgrade(cfg, "0016_model_prefs_usage_quota")
        engine = create_engine(db_url)
        try:
            insp = inspect(engine)
            assert "research_documents" not in insp.get_table_names()
            assert "documents_scoped" not in {c["name"] for c in insp.get_columns("research")}
        finally:
            engine.dispose()
        command.upgrade(cfg, "head")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
