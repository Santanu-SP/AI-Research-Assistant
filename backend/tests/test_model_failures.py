"""Failed model calls are recorded and explained without leaking keys."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.research import Research
from app.models.telemetry import TelemetryEvent
from app.providers.base import (
    AuthenticationError,
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ProviderTimeoutError,
    RateLimitError,
    model_error_type,
    redact_secrets,
)
from app.providers.router import CentralizedLLMRouter
from test_rag_api import candidates, install_pipeline_fakes


class _Failing(LLMProviderAdapter):
    def __init__(self, name: str, model: str, error: Exception) -> None:
        self.provider_name = name
        self.default_model = model
        self._error = error

    def is_configured(self, api_key_override: str | None = None) -> bool:
        return True

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise self._error


def test_redact_secrets_hides_keys() -> None:
    text = (
        "API key not valid: AIzaSyA1234567890abcdefghijklmnopqr "
        "Bearer sk-or-v1-abcdef1234567890 key=supersecretvalue"
    )
    cleaned = redact_secrets(text)
    assert "AIza" not in cleaned
    assert "sk-or-v1" not in cleaned
    assert "supersecretvalue" not in cleaned
    assert cleaned.count("[hidden]") == 3


def test_error_types() -> None:
    assert model_error_type(RateLimitError("gemini", "quota")) == "quota"
    assert model_error_type(AuthenticationError("gemini", "bad key")) == "auth"
    assert model_error_type(ProviderTimeoutError("gemini", "slow")) == "timeout"
    assert model_error_type(ValueError("x")) == "other"


def test_router_reports_each_failed_attempt_safely() -> None:
    router = CentralizedLLMRouter(
        [
            _Failing("gemini", "gemini-2.5-pro", RateLimitError("gemini", "quota for AIzaSyA1234567890abcdefghijk", status_code=429)),
            _Failing("openrouter", "openrouter/free", AuthenticationError("openrouter", "bad key", status_code=401)),
        ],
        max_transient_retries=0,
    )
    with pytest.raises(AppError) as caught:
        router.generate(LLMRequest(system_prompt="s", user_prompt="u"))
    error = caught.value
    assert error.code == "generation_unavailable"
    assert "AIza" not in error.message
    failures = error.details["modelFailures"]
    assert [(f["provider"], f["model"], f["errorType"]) for f in failures] == [
        ("gemini", "gemini-2.5-pro", "quota"),
        ("openrouter", "openrouter/free", "auth"),
    ]


def _quota_failure(question, evidence):
    raise AppError(
        "All configured LLM providers failed (gemini: quota)",
        status_code=503,
        code="generation_unavailable",
        details={
            "modelFailures": [
                {"provider": "gemini", "model": "gemini-2.5-pro", "errorType": "quota", "usedByok": True},
                {"provider": "openrouter", "model": "openrouter/free", "errorType": "timeout", "usedByok": False},
            ]
        },
    )


def test_failed_run_stores_the_reason_and_logs_telemetry(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    generator, _ = install_pipeline_fakes(monkeypatch, candidates())
    generator.generate = _quota_failure
    queued = client.post("/api/v1/research/jobs", json={"query": "What does the evidence show?"})
    research_id = queued.json()["id"]
    client.app.state.job_worker.run_until_empty()

    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "failed"
    assert progress["failureReason"] == "model_unavailable"
    assert progress["failureProvider"] == "gemini"
    assert progress["failureModel"] == "gemini-2.5-pro"
    assert progress["failureType"] == "quota"

    events = db_session.scalars(
        select(TelemetryEvent).where(TelemetryEvent.success.is_(False))
    ).all()
    assert sorted((e.provider, e.error_code) for e in events) == [
        ("gemini", "quota"),
        ("openrouter", "timeout"),
    ]
    assert all(e.details["research_id"] == research_id for e in events)

    # Trying again clears the old reason.
    generator.generate = lambda question, evidence: "The studies report improvement [S1] [S2]."
    assert client.post(f"/api/v1/research/{research_id}/retry", json={}).status_code == 202
    db_session.expire_all()
    record = db_session.get(Research, UUID(research_id))
    assert record.failure_type is None
    client.app.state.job_worker.run_until_empty()
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "completed"
    assert progress["failureType"] is None
