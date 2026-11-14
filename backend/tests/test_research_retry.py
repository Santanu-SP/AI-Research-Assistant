"""Running a failed research item again, and not creating duplicates."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.job import BackgroundJob
from app.models.research import Research
from test_rag_api import candidates, install_pipeline_fakes


def _model_down(question, evidence):
    raise AppError(
        "No LLM providers are configured or available",
        status_code=503,
        code="generation_unavailable",
    )


def _failed_job(client: TestClient, monkeypatch, question="What does the evidence show?"):
    generator, _ = install_pipeline_fakes(monkeypatch, candidates())
    generator.generate = _model_down
    queued = client.post("/api/v1/research/jobs", json={"query": question})
    assert queued.status_code == 202, queued.text
    client.app.state.job_worker.run_until_empty()
    return generator, queued.json()["id"]


def test_failed_run_explains_why_and_retries_in_place(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    generator, research_id = _failed_job(client, monkeypatch)
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "failed"
    assert progress["failureReason"] == "model_unavailable"

    # The model is back; "Try again" reuses the same research record.
    generator.generate = lambda question, evidence: "The studies report improvement [S1] [S2]."
    retried = client.post(f"/api/v1/research/{research_id}/retry", json={})
    assert retried.status_code == 202, retried.text
    assert retried.json()["id"] == research_id
    assert retried.json()["status"] == "researching"

    assert client.app.state.job_worker.run_until_empty() == 1
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "completed"
    assert progress["failureReason"] is None

    history = client.get("/api/v1/research").json()
    assert history["total"] == 1
    assert db_session.scalar(select(func.count()).select_from(Research)) == 1


def test_retry_can_run_an_edited_question_on_the_same_item(client: TestClient, monkeypatch) -> None:
    _, research_id = _failed_job(client, monkeypatch, "What does the evidence show?")
    retried = client.post(
        f"/api/v1/research/{research_id}/retry",
        json={"query": "Which study reports the largest improvement?", "researchDepth": "deep"},
    )
    assert retried.status_code == 202, retried.text
    body = retried.json()
    assert body["id"] == research_id
    assert body["question"] == "Which study reports the largest improvement?"
    assert body["title"] == "Which study reports the largest improvement?"
    assert body["researchDepth"] == "deep"
    assert client.get("/api/v1/research").json()["total"] == 1


def test_only_failed_research_can_be_retried(client: TestClient, monkeypatch) -> None:
    install_pipeline_fakes(monkeypatch, candidates())
    queued = client.post("/api/v1/research/jobs", json={"query": "What does the evidence show?"})
    research_id = queued.json()["id"]
    running = client.post(f"/api/v1/research/{research_id}/retry")
    assert running.status_code == 409
    assert running.json()["error"]["code"] == "research_not_retryable"

    client.app.state.job_worker.run_until_empty()
    done = client.post(f"/api/v1/research/{research_id}/retry")
    assert done.status_code == 409
    assert done.json()["error"]["code"] == "research_not_retryable"


def test_retry_of_someone_elses_research_is_not_found(
    client: TestClient, anonymous_client: TestClient, monkeypatch
) -> None:
    _, research_id = _failed_job(client, monkeypatch)
    account = {"email": "other-retry@example.com", "password": "another-pass-123"}
    anonymous_client.post("/api/v1/auth/register", json={"name": "Other", **account})
    assert anonymous_client.post("/api/v1/auth/login", json=account).status_code == 200
    response = anonymous_client.post(f"/api/v1/research/{research_id}/retry")
    assert response.status_code == 404


def test_double_submitted_job_creates_one_research_and_one_job(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    install_pipeline_fakes(monkeypatch, candidates())
    payload = {"query": "  What does the evidence show? ", "researchDepth": "standard"}
    first = client.post("/api/v1/research/jobs", json=payload)
    second = client.post("/api/v1/research/jobs", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert db_session.scalar(select(func.count()).select_from(Research)) == 1
    assert db_session.scalar(select(func.count()).select_from(BackgroundJob)) == 1

    # A different depth is a different request.
    other = client.post(
        "/api/v1/research/jobs", json={**payload, "researchDepth": "deep"}
    )
    assert other.json()["id"] != first.json()["id"]


def test_inline_query_points_at_the_run_already_in_progress(client: TestClient, monkeypatch) -> None:
    install_pipeline_fakes(monkeypatch, candidates())
    queued = client.post("/api/v1/research/jobs", json={"query": "What does the evidence show?"})
    again = client.post("/api/v1/research/query", json={"query": "What does the evidence show?"})
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "research_already_running"
    assert error["details"]["researchId"] == queued.json()["id"]


def test_failed_inline_query_returns_the_research_id(client: TestClient, monkeypatch) -> None:
    generator, _ = install_pipeline_fakes(monkeypatch, candidates())
    generator.generate = _model_down
    response = client.post("/api/v1/research/query", json={"query": "What does the evidence show?"})
    assert response.status_code == 503
    research_id = response.json()["error"]["details"]["researchId"]
    status = client.get(f"/api/v1/research/{research_id}/status").json()
    assert status["status"] == "failed"

    generator.generate = lambda question, evidence: "The studies report improvement [S1] [S2]."
    assert client.post(f"/api/v1/research/{research_id}/retry").status_code == 202
    client.app.state.job_worker.run_until_empty()
    assert client.get(f"/api/v1/research/{research_id}/status").json()["status"] == "completed"
    assert client.get("/api/v1/research").json()["total"] == 1


def test_progress_reports_document_readiness(client: TestClient) -> None:
    created = client.post("/api/v1/research/jobs", json={"query": "Anything at all?"}).json()
    progress = client.get(f"/api/v1/research/{created['id']}/status").json()
    assert progress["documentsReady"] == 0
    assert progress["documentsPreparing"] == 0


def test_retry_uses_a_local_model_switched_on_after_the_failure(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    _, research_id = _failed_job(client, monkeypatch)
    turned_on = client.post("/api/v1/auth/api-keys/local-fallback", json={"connected": True})
    assert turned_on.status_code == 200, turned_on.text

    assert client.post(f"/api/v1/research/{research_id}/retry", json={}).status_code == 202
    record = db_session.get(Research, UUID(research_id))
    db_session.refresh(record)
    assert record.local_fallback_enabled is True
