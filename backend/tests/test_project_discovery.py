"""Projects can opt in to finding sources online for a question."""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.research import Research
from app.schemas.discovery import DiscoverySearchResponse
from app.services.discovery import service as discovery_service
from app.services.rag import query as rag_service
from test_architecture_upgrade import DeterministicEmbeddingService, KeywordAwareReranker
from test_collaboration_realtime import _register_and_login
from test_controlled_discovery import _build_mock_transport
from test_documents_api import PDF_MIME, make_pdf

QUESTION = "How does self-attention work in Transformer models?"


class _RecordingGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.evidence_documents: list[set[UUID]] = []

    def generate(self, question, evidence, **_kwargs) -> str:
        self.calls += 1
        self.evidence_documents.append({item.document_id for item in evidence})
        return f"Self-attention replaces recurrence in Transformer models [{evidence[0].source_id}]."


def _fake_models(client: TestClient, monkeypatch) -> _RecordingGenerator:
    settings = client.app.state.settings
    settings.embedding_enabled = True
    settings.allow_sqlite_retrieval_fallback = True
    embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda _s: KeywordAwareReranker())
    generator = _RecordingGenerator()
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)
    return generator


def _fake_internet(monkeypatch) -> list[str]:
    pdf_bytes = make_pdf(
        "1 INTRODUCTION\nSelf-attention replaces recurrence in Transformer models and improves parallelization.",
        title="Attention Is All You Need",
    )
    requested: list[str] = []
    transport = _build_mock_transport(pdf_bytes=pdf_bytes, requested_urls=requested)
    # Every request is answered by the fake transport, so skip real DNS
    # lookups (the SSRF scheme and credential checks still run).
    real_validate = discovery_service.validate_public_url
    monkeypatch.setattr(
        discovery_service,
        "validate_public_url",
        lambda url, **_kw: real_validate(url, resolver=lambda _host: ["93.184.215.14"]),
    )
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: real_client(transport=transport))
    return requested


def _project_documents(session: Session, project_id: str) -> list[Document]:
    session.expire_all()
    return list(session.scalars(select(Document).where(Document.project_id == UUID(project_id))))


def _ask(client: TestClient, project_id: str, question: str = QUESTION, **extra) -> str:
    response = client.post(
        "/api/v1/research/jobs",
        json={"query": question, "projectId": project_id, "autoDiscover": True, **extra},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_empty_project_can_ask_and_found_sources_are_added_to_the_project(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    generator = _fake_models(client, monkeypatch)
    requested = _fake_internet(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Empty project"}).json()

    research_id = _ask(client, project["id"])
    # Starting the question does not wait on the internet.
    assert requested == []
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["autoDiscover"] is True
    assert "Finding sources" in [step["title"] for step in progress["steps"]]

    assert client.app.state.job_worker.run_until_empty() == 1
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "completed", progress
    assert generator.calls == 1

    documents = _project_documents(db_session, project["id"])
    assert documents, "found sources should be saved in the project's files"
    assert all(doc.project_id == UUID(project["id"]) for doc in documents)

    record = db_session.get(Research, UUID(research_id))
    # The run is linked to what it found, but still reads the whole project.
    assert record.documents_scoped is False
    assert set(record.document_ids) <= {doc.id for doc in documents}
    assert record.document_ids

    files = client.get(f"/api/v1/projects/{project['id']}/documents").json()
    listed = files["items"] if isinstance(files, dict) else files
    assert {item["id"] for item in listed} == {str(doc.id) for doc in documents}

    report = client.get(f"/api/v1/research/{research_id}/report").json()
    assert report["report"]["sourceCount"] >= 1


def test_answers_use_project_files_and_found_sources_without_duplicates(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    generator = _fake_models(client, monkeypatch)
    _fake_internet(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Mixed project"}).json()
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/documents",
        files={"file": ("notes.pdf", make_pdf("My notes: self-attention in Transformer models compares every token."), PDF_MIME)},
    )
    assert uploaded.status_code == 201, uploaded.text
    client.app.state.job_worker.run_until_empty()
    uploaded_id = UUID(uploaded.json()["id"])

    first = _ask(client, project["id"])
    client.app.state.job_worker.run_until_empty()
    assert client.get(f"/api/v1/research/{first}/status").json()["status"] == "completed"
    after_first = _project_documents(db_session, project["id"])
    assert len(after_first) > 1
    # The project's own file was still allowed into the answer.
    assert generator.evidence_documents[-1] <= {doc.id for doc in after_first}
    assert uploaded_id in {doc.id for doc in after_first}

    # Same sources found again: nothing is downloaded or saved twice.
    second = _ask(client, project["id"], "What does self-attention replace in Transformer models?")
    client.app.state.job_worker.run_until_empty()
    assert client.get(f"/api/v1/research/{second}/status").json()["status"] == "completed"
    after_second = _project_documents(db_session, project["id"])
    assert sorted(doc.id for doc in after_second) == sorted(doc.id for doc in after_first)
    record = db_session.get(Research, UUID(second))
    assert record.documents_scoped is False
    assert record.document_ids, "the second run is still linked to the matching sources"


def test_new_sources_per_question_are_capped(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _fake_models(client, monkeypatch)
    _fake_internet(monkeypatch)
    client.app.state.settings.project_discovery_source_limit = 1
    project = client.post("/api/v1/projects", json={"name": "Capped"}).json()

    research_id = _ask(client, project["id"])
    client.app.state.job_worker.run_until_empty()
    assert client.get(f"/api/v1/research/{research_id}/status").json()["status"] == "completed"
    assert len(_project_documents(db_session, project["id"])) == 1


def test_nothing_found_falls_back_to_project_files_or_fails_when_empty(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    generator = _fake_models(client, monkeypatch)

    def no_results(_session, *, query, scope, **_kwargs):
        return DiscoverySearchResponse(query=query, scope=scope, items=[])

    monkeypatch.setattr(discovery_service, "search_and_annotate", no_results)

    empty = client.post("/api/v1/projects", json={"name": "Nothing here"}).json()
    failed = _ask(client, empty["id"])
    client.app.state.job_worker.run_until_empty()
    progress = client.get(f"/api/v1/research/{failed}/status").json()
    assert progress["status"] == "failed"
    assert progress["failureReason"] == "no_discoverable_sources"

    with_files = client.post("/api/v1/projects", json={"name": "Has files"}).json()
    uploaded = client.post(
        f"/api/v1/projects/{with_files['id']}/documents",
        files={"file": ("notes.pdf", make_pdf("Self-attention in Transformer models compares tokens."), PDF_MIME)},
    )
    assert uploaded.status_code == 201
    client.app.state.job_worker.run_until_empty()
    research_id = _ask(client, with_files["id"])
    client.app.state.job_worker.run_until_empty()
    assert client.get(f"/api/v1/research/{research_id}/status").json()["status"] == "completed"
    assert generator.evidence_documents[-1] == {UUID(uploaded.json()["id"])}


def test_switch_off_keeps_project_answers_offline(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _fake_models(client, monkeypatch)
    requested = _fake_internet(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Offline"}).json()
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/documents",
        files={"file": ("notes.pdf", make_pdf("Self-attention in Transformer models compares tokens."), PDF_MIME)},
    )
    assert uploaded.status_code == 201
    client.app.state.job_worker.run_until_empty()

    response = client.post(
        "/api/v1/research/jobs",
        json={"query": QUESTION, "projectId": project["id"]},
    )
    assert response.status_code == 202
    client.app.state.job_worker.run_until_empty()
    record = db_session.get(Research, UUID(response.json()["id"]))
    assert record.discovery_scope is None
    assert [url for url in requested if "openalex" in url or "crossref" in url] == []
    assert len(_project_documents(db_session, project["id"])) == 1


def test_only_owners_and_editors_can_find_sources_online(
    test_app: FastAPI,
    monkeypatch,
) -> None:
    requested = _fake_internet(monkeypatch)
    owner, _ = _register_and_login(test_app, name="Owner", email="owner-pd@example.com")
    viewer, _ = _register_and_login(test_app, name="Viewer", email="viewer-pd@example.com")
    editor, _ = _register_and_login(test_app, name="Editor", email="editor-pd@example.com")
    with owner, viewer, editor:
        pid = owner.post("/api/v1/projects", json={"name": "Shared"}).json()["id"]
        for email, role in (("viewer-pd@example.com", "viewer"), ("editor-pd@example.com", "editor")):
            added = owner.post(f"/api/v1/projects/{pid}/members", json={"email": email, "role": role})
            assert added.status_code == 201, added.text

        for path in ("/api/v1/research/jobs", "/api/v1/research/query"):
            refused = viewer.post(
                path,
                json={"query": QUESTION, "projectId": pid, "autoDiscover": True},
            )
            assert refused.status_code == 403, refused.text
        assert requested == []

        allowed = editor.post(
            "/api/v1/research/jobs",
            json={"query": QUESTION, "projectId": pid, "autoDiscover": True},
        )
        assert allowed.status_code == 202, allowed.text


def test_project_discovery_is_refused_when_switched_off_on_the_server(client: TestClient) -> None:
    client.app.state.settings.discovery_enabled = False
    project = client.post("/api/v1/projects", json={"name": "No discovery"}).json()
    response = client.post(
        "/api/v1/research/jobs",
        json={"query": QUESTION, "projectId": project["id"], "autoDiscover": True},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "discovery_disabled"


def test_editing_a_failed_question_searches_again(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    _fake_models(client, monkeypatch)
    _fake_internet(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Retry"}).json()
    research_id = _ask(client, project["id"])
    client.app.state.job_worker.run_until_empty()
    record = db_session.get(Research, UUID(research_id))
    assert record.document_ids

    # Make the run look failed, then ask an edited question in its place.
    from app.domain.research import ResearchStatus

    record.status = ResearchStatus.FAILED
    db_session.commit()
    retried = client.post(
        f"/api/v1/research/{research_id}/retry",
        json={"query": "What does self-attention replace?"},
    )
    assert retried.status_code == 202, retried.text
    db_session.expire_all()
    assert db_session.get(Research, UUID(research_id)).document_ids == []


def test_inline_project_question_can_also_find_sources(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    generator = _fake_models(client, monkeypatch)
    _fake_internet(monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "Inline"}).json()
    response = client.post(
        "/api/v1/research/query",
        json={"query": QUESTION, "projectId": project["id"], "autoDiscover": True, "researchDepth": "quick"},
    )
    assert response.status_code == 201, response.text
    assert generator.calls == 1
    assert response.json()["citations"]
    documents = _project_documents(db_session, project["id"])
    assert documents
    record = db_session.get(Research, UUID(response.json()["researchId"]))
    assert record.documents_scoped is False
