"""Background worker, retries, recovery, and the bug fixes around them."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.domain.documents import DocumentStatus
from app.models.document import Document
from app.models.job import BackgroundJob
from app.models.report import Source
from app.services.ingestion import pipeline as ingestion_service
from app.services.jobs import queue as job_queue
from app.services.jobs.worker import INTERRUPTED_MESSAGE, JobWorker
from test_documents_api import make_pdf, upload_document
from test_rag_api import candidates, install_pipeline_fakes


def _background(client: TestClient) -> JobWorker:
    settings = client.app.state.settings
    settings.ingestion_mode = "background"
    return client.app.state.job_worker


# --- background ingestion --------------------------------------------------


def test_background_upload_returns_202_then_worker_indexes_it(client: TestClient) -> None:
    worker = _background(client)
    response = upload_document(client, content=make_pdf("Queued evidence about enzymes."))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "uploaded"

    assert worker.run_until_empty() == 1
    document = client.get(f"/api/v1/documents/{body['id']}").json()
    assert document["status"] == "indexed"
    assert document["chunkCount"] >= 1


def test_background_failure_is_recorded_without_retrying_forever(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    worker = _background(client)
    response = upload_document(client, content=b"%PDF-1.7\ncorrupted")
    assert response.status_code == 202
    worker.run_until_empty()
    document = client.get(f"/api/v1/documents/{response.json()['id']}").json()
    assert document["status"] == "failed"
    with db_session_factory() as session:
        job = session.scalar(select(BackgroundJob))
        assert job is not None and job.state == "failed" and job.attempts == 1


def test_unexpected_worker_crash_is_retried_then_failed(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    calls = []

    def flaky(session, target_id, settings):
        calls.append(target_id)
        raise RuntimeError("worker blew up")

    settings = client.app.state.settings
    settings.job_max_attempts = 2
    worker = JobWorker(client.app.state.db_session_factory, settings, handlers={"flaky": flaky})
    with db_session_factory() as session:
        job = job_queue.enqueue(session, "flaky", UUID(int=1))
        job_id = job.id
    assert worker.run_once() is True
    with db_session_factory() as session:
        job = session.get(BackgroundJob, job_id)
        assert job.state == "queued" and job.attempts == 1
        session.execute(update(BackgroundJob).values(run_after=utc_now()))
        session.commit()
    assert worker.run_once() is True
    with db_session_factory() as session:
        job = session.get(BackgroundJob, job_id)
        assert job.state == "failed" and job.attempts == 2 and "worker blew up" in job.last_error
    assert len(calls) == 2


def test_stale_running_job_is_requeued_and_processed(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    worker = _background(client)
    response = upload_document(client, content=make_pdf("Crash recovery evidence."))
    document_id = response.json()["id"]
    with db_session_factory() as session:
        # Simulate a worker that claimed the job and then died.
        assert job_queue.claim_next(session) is not None
        session.execute(
            update(BackgroundJob).values(locked_at=utc_now() - timedelta(hours=1))
        )
        session.execute(
            update(Document).values(status=DocumentStatus.PROCESSING)
        )
        session.commit()
    summary = worker.run_maintenance()
    assert summary["jobs_requeued"] == 1
    worker.run_until_empty()
    assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "indexed"


def test_document_stuck_in_processing_without_a_job_is_failed(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    response = upload_document(client, content=make_pdf("Inline evidence."))
    document_id = UUID(response.json()["id"])
    with db_session_factory() as session:
        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.PROCESSING, updated_at=utc_now() - timedelta(hours=2))
        )
        session.commit()
    summary = client.app.state.job_worker.run_maintenance()
    assert summary["documents_unstuck"] == 1
    body = client.get(f"/api/v1/documents/{document_id}").json()
    assert body["status"] == "failed"
    assert body["processingError"] == INTERRUPTED_MESSAGE


# --- failed documents can be retried ----------------------------------------


def test_reuploading_a_failed_document_replaces_it(
    client: TestClient, db_session_factory: sessionmaker[Session], upload_dir: Path
) -> None:
    content = b"%PDF-1.7\ncorrupted"
    assert upload_document(client, content=content).status_code == 422
    second = upload_document(client, content=content)
    assert second.status_code == 422  # processed again instead of a 409
    with db_session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
    assert len(list(upload_dir.iterdir())) == 1


def test_retry_endpoint_reprocesses_a_failed_document(client: TestClient, monkeypatch) -> None:
    def broken_embeddings(*args, **kwargs):
        raise RuntimeError("embedding backend offline")

    monkeypatch.setattr(ingestion_service, "_embed_nodes", broken_embeddings)
    failed = upload_document(client, content=make_pdf("Retry evidence."))
    assert failed.status_code == 422
    document_id = client.get("/api/v1/documents").json()["items"][0]["id"]
    monkeypatch.undo()

    retried = client.post(f"/api/v1/documents/{document_id}/retry")
    assert retried.status_code == 201, retried.text
    assert retried.json()["status"] == "indexed"
    again = client.post(f"/api/v1/documents/{document_id}/retry")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "document_not_retryable"


# --- archived projects -------------------------------------------------------


def test_documents_in_archived_projects_leave_the_global_library(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Old project"}).json()
    assert client.post(
        f"/api/v1/projects/{project['id']}/documents",
        files={"file": ("p.pdf", make_pdf("Archived evidence."), "application/pdf")},
    ).status_code == 201
    upload_document(client, content=make_pdf("Library evidence."))
    assert client.get("/api/v1/documents").json()["total"] == 2
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    library = client.get("/api/v1/documents").json()
    assert library["total"] == 1
    assert library["items"][0]["projectId"] is None


# --- research runs -----------------------------------------------------------


def test_research_job_runs_in_background_and_reports_source_count(
    client: TestClient, monkeypatch
) -> None:
    generator, _ = install_pipeline_fakes(monkeypatch, candidates())
    queued = client.post("/api/v1/research/jobs", json={"query": "What does the evidence show?"})
    assert queued.status_code == 202, queued.text
    research_id = queued.json()["id"]
    assert queued.json()["status"] == "researching"
    assert generator.calls == 0

    assert client.app.state.job_worker.run_until_empty() == 1
    assert generator.calls == 1
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "completed"
    report = client.get(f"/api/v1/research/{research_id}/report").json()
    assert report["report"]["sourceCount"] == 2

    assert client.get(f"/api/v1/research/{research_id}").json()["sourceCount"] == 2
    listed = client.get("/api/v1/research").json()["items"]
    assert listed[0]["sourceCount"] == 2


def test_answer_without_valid_citations_is_reported_as_insufficient(
    client: TestClient, monkeypatch
) -> None:
    generator, _ = install_pipeline_fakes(monkeypatch, candidates())
    generator.generate = lambda question, evidence: "Confident claim [S42]. Another claim."
    response = client.post("/api/v1/research/query", json={"query": "Anything?"})
    assert response.status_code == 201
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["citations"] == []
    assert "do not contain enough relevant evidence" in body["answer"]


def test_sources_count_is_zero_before_a_report_exists(
    client: TestClient, db_session: Session
) -> None:
    created = client.post("/api/v1/research", json={"question": "Draft question"}).json()
    assert created["sourceCount"] == 0
    assert db_session.scalar(select(Source)) is None
