"""Tests for per-user model usage reporting and fair-share daily quotas."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.providers.base import LLMResponse, TokenUsage
from app.schemas.retrieval import RetrievalCandidate
from app.services.observability.telemetry import record_telemetry_event
from app.services.rag import query as rag_service
from tests.conftest import FRONTEND_HEADERS


class _FakeReranker:
    def rerank(self, query: str, items: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        return [
            item.model_copy(update={"rerank_score": 5.0 - index})
            for index, item in enumerate(items)
        ]


def _install_retrieval_fakes(monkeypatch) -> None:
    items = [
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            paper_title="Attention Is All You Need",
            authors=["Vaswani et al."],
            doi=None,
            page=1,
            section="Introduction",
            text="Self-attention relates different positions of a single sequence [S1].",
            vector_score=0.92,
            keyword_score=0.81,
            hybrid_score=0.89,
        )
    ]

    def fake_retrieve(session, user_id, query, settings, *, project_id=None):
        return items

    monkeypatch.setattr(rag_service.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda *_args, **_kwargs: _FakeReranker())


def test_user_model_usage_and_fair_share_daily_cap_scaling(
    client: TestClient,
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    settings = test_app.state.settings
    settings.llm_daily_system_request_pool = 6
    _install_retrieval_fakes(monkeypatch)

    me = client.get("/api/v1/auth/me").json()
    user_1_id = UUID(me["id"])

    # With 1 enrolled user and pool=6, daily cap for User 1 is 6.
    initial_usage = client.get("/api/v1/auth/api-keys/usage").json()
    assert initial_usage["enrolledUsers"] == 1
    assert initial_usage["systemPoolTotal"] == 6
    assert initial_usage["userDailyRequestCap"] == 6
    assert initial_usage["userRequestsRemainingToday"] == 6

    # Enroll User 2 -> fair share immediately divides pool (6 // 2 = 3 per user).
    with TestClient(test_app, headers=FRONTEND_HEADERS) as client_2:
        reg_2 = client_2.post(
            "/api/v1/auth/register",
            json={
                "name": "Second User",
                "email": "user2@example.com",
                "password": "test-password-123",
            },
        )
        assert reg_2.status_code == 201
        assert client_2.post(
            "/api/v1/auth/login",
            json={"email": "user2@example.com", "password": "test-password-123"},
        ).status_code == 200
        user_2_id = UUID(reg_2.json()["id"])

        # User 1 consumes 4 shared requests (recorded via telemetry/research); 2 global requests left!
        with db_session_factory() as db:
            for _ in range(4):
                record_telemetry_event(
                    db,
                    event_type="llm_generation",
                    operation="research_answer",
                    provider="gemini",
                    model="gemini-3.8-flash",
                    status="success",
                    prompt_tokens=100,
                    completion_tokens=40,
                    user_id=user_1_id,
                    metadata={"used_byok": False, "is_local": False},
                )

        # User 2's fair share would be 3, but only 2 shared requests remain in pool -> cap becomes 2!
        u2_usage = client_2.get("/api/v1/auth/api-keys/usage").json()
        assert u2_usage["enrolledUsers"] == 2
        assert u2_usage["systemPoolUsedToday"] == 4
        assert u2_usage["systemPoolRemaining"] == 2
        assert u2_usage["userDailyRequestCap"] == 2
        assert u2_usage["userRequestsRemainingToday"] == 2

        # Run 2 real queries through /research/query with a mocked generator recording provider+model usage.
        class StubGenerator:
            def __init__(self, provider: str, model: str, *, used_byok: bool = False) -> None:
                self.provider = provider
                self.model = model
                self.used_byok = used_byok
                self.last_response: LLMResponse | None = None

            def generate(self, question: str, evidence, **kwargs) -> str:
                self.last_response = LLMResponse(
                    provider=self.provider,
                    model=self.model,
                    content="Self-attention relates sequence positions [S1].",
                    usage=TokenUsage(prompt_tokens=150, completion_tokens=50, total_tokens=200),
                    used_byok=self.used_byok,
                )
                return self.last_response.content

        monkeypatch.setattr(
            rag_service,
            "generation_service_for",
            lambda *_args, **_kwargs: StubGenerator("gemini", "gemini-2.5-flash"),
        )
        for idx in range(2):
            ok = client_2.post(
                "/api/v1/research/query",
                json={"query": f"Explain self-attention {idx}", "researchDepth": "quick"},
            )
            assert ok.status_code == 201, ok.text

        # After 2 shared requests, remaining == 0 -> next shared request returns 429 daily_model_quota_exceeded.
        blocked = client_2.post(
            "/api/v1/research/query",
            json={"query": "Third shared request should be capped", "researchDepth": "quick"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "daily_model_quota_exceeded"

        # Local Ollama bypasses shared daily cap even when pool is exhausted.
        monkeypatch.setattr(
            rag_service,
            "generation_service_for",
            lambda *_args, **_kwargs: StubGenerator("ollama", "llama3.2:3b", used_byok=False),
        )
        local_ok = client_2.post(
            "/api/v1/research/query",
            json={
                "query": "Local model request after shared cap",
                "researchDepth": "quick",
                "preferredProvider": "ollama",
            },
        )
        assert local_ok.status_code == 201, local_ok.text

        # Explicit BYOK provider ALSO bypasses shared daily cap.
        assert client_2.put(
            "/api/v1/auth/api-keys/openai",
            json={"apiKey": "sk-proj-user2-testkey123456"},
        ).status_code == 200
        monkeypatch.setattr(
            rag_service,
            "generation_service_for",
            lambda *_args, **_kwargs: StubGenerator("openai", "gpt-4o-mini", used_byok=True),
        )
        byok_ok = client_2.post(
            "/api/v1/research/query",
            json={
                "query": "BYOK OpenAI request after shared cap",
                "researchDepth": "quick",
                "preferredProvider": "openai",
            },
        )
        assert byok_ok.status_code == 201, byok_ok.text

        # Verify /auth/api-keys/usage and /auth/api-keys/models-status reflect all models used accurately.
        final_usage = client_2.get("/api/v1/auth/api-keys/usage").json()
        assert final_usage["sharedRequestsUsedToday"] == 2
        assert final_usage["localRequestsToday"] == 1
        assert final_usage["byokRequestsToday"] == 1
        assert final_usage["totalRequestsToday"] == 4
        assert final_usage["totalTokensToday"] == 800
        assert final_usage["userRequestsRemainingToday"] == 0
        models_used = {(m["provider"], m["modelName"]): m for m in final_usage["models"]}
        assert models_used[("gemini", "gemini-2.5-flash")]["requestsToday"] == 2
        assert models_used[("ollama", "llama3.2:3b")]["requestsToday"] == 1
        assert models_used[("openai", "gpt-4o-mini")]["requestsToday"] == 1

        status_res = client_2.get("/api/v1/auth/api-keys/models-status")
        assert status_res.status_code == 200
        assert status_res.json()["usage"]["sharedRequestsUsedToday"] == 2
