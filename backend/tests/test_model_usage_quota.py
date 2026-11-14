"""Tests for per-user model usage reporting and fair-share daily quotas."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.providers.base import LLMResponse, TokenUsage
from app.schemas.retrieval import RetrievalCandidate
from app.services.observability.telemetry import record_telemetry_event
from app.services.observability.usage import record_model_usage, reserve_shared_quota_slot
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

        # User 1 consumes 4 shared requests; 2 global requests left!
        with db_session_factory() as db:
            for _ in range(4):
                record_model_usage(
                    db,
                    user_id=user_1_id,
                    provider="gemini",
                    model_name="gemini-3.8-flash",
                    usage_source="shared",
                    input_tokens=100,
                    output_tokens=40,
                    increment_shared_quota=True,
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
            json={"apiKey": "sk-" + "user2-test-key"},
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


def _init_app_db(app) -> None:
    from app.db.base import Base

    Base.metadata.create_all(app.state.db_engine)


def test_over_limit_fake_byok_key_cannot_fall_through_to_shared_providers(
    tmp_path,
    monkeypatch,
) -> None:
    """Once daily shared quota is exhausted, failing BYOK keys must never fall back to server keys."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from app.providers.base import AuthenticationError, LLMProviderAdapter, LLMRequest, LLMResponse, TokenUsage
    from app.providers.router import CentralizedLLMRouter
    from app.services.rag.generation import GenerationService

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'fake_byok_bypass.db'}",
        app_environment="test",
        worker_enabled=False,
        llm_daily_system_request_pool=1,
        gemini_api_key="server-shared-gemini-key",
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    _init_app_db(app)

    with TestClient(app, headers=FRONTEND_HEADERS) as client:
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "User", "email": "bypass@example.com", "password": "test-password-123"},
        )
        assert reg.status_code == 201
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "bypass@example.com", "password": "test-password-123"},
        ).status_code == 200
        user_id = UUID(reg.json()["id"])

        # Exhaust the daily quota of 1 shared request
        with app.state.db_session_factory() as db:
            ok, _, _ = reserve_shared_quota_slot(db, user_id=user_id, settings=settings)
            assert ok is True

        # User saves a made-up fake BYOK OpenAI key
        fake_byok_key = "sk-" + "invalid-test-key"
        save_fake = client.put(
            "/api/v1/auth/api-keys/openai",
            json={"apiKey": fake_byok_key},
        )
        assert save_fake.status_code == 200

        call_log: list[tuple[str, str | None]] = []

        class FakeOpenAI(LLMProviderAdapter):
            provider_name = "openai"
            default_model = "gpt-4o-mini"

            def is_configured(self, api_key_override: str | None = None) -> bool:
                return bool(api_key_override)

            def generate(self, request: LLMRequest) -> LLMResponse:
                call_log.append(("openai", request.api_key_override))
                raise AuthenticationError("openai", "Incorrect API key provided", status_code=401)

        class SharedGemini(LLMProviderAdapter):
            provider_name = "gemini"
            default_model = "gemini-2.5-flash"

            def is_configured(self, api_key_override: str | None = None) -> bool:
                return True

            def generate(self, request: LLMRequest) -> LLMResponse:
                call_log.append(("gemini", request.api_key_override))
                return LLMResponse(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    content="Leaked onto server key [S1].",
                    usage=TokenUsage(10, 10, 20),
                )

        def make_router() -> CentralizedLLMRouter:
            shared_gem = SharedGemini()
            return CentralizedLLMRouter(
                [shared_gem],
                catalog={"openai": FakeOpenAI(), "gemini": shared_gem},
                max_transient_retries=0,
            )

        monkeypatch.setattr(
            "app.services.rag.query.generation_service_for",
            lambda *_a, **_kw: GenerationService(router=make_router()),
        )
        _install_retrieval_fakes(monkeypatch)

        # 1) Picking fake OpenAI BYOK must fail on OpenAI and NEVER fall through to shared Gemini
        res_fake_openai = client.post(
            "/api/v1/research/query",
            json={
                "query": "Attempt bypass via fake OpenAI key",
                "researchDepth": "quick",
                "preferredProvider": "openai",
            },
        )
        assert res_fake_openai.status_code == 503
        assert ("openai", fake_byok_key) in call_log
        assert all(prov != "gemini" for prov, _ in call_log)

        # 2) Using auto mode with only the fake OpenAI key also must NEVER touch shared Gemini
        call_log.clear()
        res_auto = client.post(
            "/api/v1/research/query",
            json={
                "query": "Attempt bypass via auto mode",
                "researchDepth": "quick",
            },
        )
        assert res_auto.status_code == 503
        assert ("openai", fake_byok_key) in call_log
        assert all(prov != "gemini" for prov, _ in call_log)

        # 3) Explicitly picking shared Gemini without Gemini BYOK is blocked immediately with 429
        call_log.clear()
        res_shared_direct = client.post(
            "/api/v1/research/query",
            json={
                "query": "Attempt direct shared provider despite OpenAI key",
                "researchDepth": "quick",
                "preferredProvider": "gemini",
            },
        )
        assert res_shared_direct.status_code == 429
        assert res_shared_direct.json()["error"]["code"] == "daily_model_quota_exceeded"
        assert call_log == []


def test_preferences_and_queued_run_options_persist_across_sessions(tmp_path, monkeypatch) -> None:
    """Provider model choices, local fallback pref, and queued run options survive DB reload."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.domain.reports import SourceType
    from app.main import create_app
    from app.models.research import Research
    from app.providers.base import LLMResponse, TokenUsage
    from app.schemas.rag import EvidenceItem, ResearchQueryRequest
    from app.services.auth import api_keys as api_key_service
    from app.services.rag import query as rag_query

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'persist_prefs.db'}",
        app_environment="test",
        worker_enabled=False,
        llm_daily_system_request_pool=10,
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    _init_app_db(app)

    with TestClient(app, headers=FRONTEND_HEADERS) as client:
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Persist", "email": "persist@example.com", "password": "test-password-123"},
        )
        assert reg.status_code == 201
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "persist@example.com", "password": "test-password-123"},
        ).status_code == 200
        user_id = UUID(reg.json()["id"])

        assert client.put(
            "/api/v1/auth/api-keys/openai",
            json={"apiKey": "sk-" + "persist-test-key"},
        ).status_code == 200
        assert client.post(
            "/api/v1/auth/api-keys/provider-model",
            json={"provider": "openai", "modelName": "gpt-4.1-mini"},
        ).status_code == 200
        assert client.post(
            "/api/v1/auth/api-keys/local-fallback",
            json={"connected": False},
        ).status_code == 200

        # Fresh independent session (simulating restart or separate worker process) reads DB state
        with app.state.db_session_factory() as worker_db:
            assert api_key_service.get_user_provider_models(worker_db, user_id) == {
                "openai": "gpt-4.1-mini"
            }
            assert api_key_service.get_local_fallback_pref(worker_db, user_id) is False

            queued = rag_query.queue_query(
                worker_db,
                user_id,
                ResearchQueryRequest(
                    query="Check persisted worker options",
                    research_depth="quick",
                    preferred_provider="openai",
                    model_override="gpt-4o",
                    local_fallback_enabled=False,
                ),
                settings,
            )
            queued_id = queued.id

        captured_calls: list[dict[str, object]] = []

        class RecordingGenerator:
            def __init__(self) -> None:
                self.last_response: LLMResponse | None = None

            def generate(self, question: str, evidence: list[EvidenceItem], **kwargs: object) -> str:
                captured_calls.append(dict(kwargs))
                self.last_response = LLMResponse(
                    provider="openai",
                    model=str(kwargs.get("model_override") or "gpt-4o-mini"),
                    content="Persisted [S1].",
                    usage=TokenUsage(20, 10, 30),
                    used_byok=True,
                )
                return self.last_response.content

        _install_retrieval_fakes(monkeypatch)

        # Execute from yet another fresh session as a separate worker would
        with app.state.db_session_factory() as exec_db:
            stored_row = exec_db.get(Research, queued_id)
            assert stored_row is not None
            assert stored_row.preferred_provider == "openai"
            assert stored_row.model_override == "gpt-4o"
            assert stored_row.local_fallback_enabled is False

            rag_query.execute_research(
                exec_db,
                queued_id,
                user_id,
                settings,
                generator=RecordingGenerator(),
                commit_intermediate=False,
            )

        assert len(captured_calls) == 1
        assert captured_calls[0]["preferred_provider"] == "openai"
        assert captured_calls[0]["model_override"] == "gpt-4o"
        assert captured_calls[0]["local_fallback_enabled"] is False
        assert captured_calls[0]["user_provider_models"] == {"openai": "gpt-4.1-mini"}


def test_quota_and_usage_work_without_telemetry_and_ignore_dormant_users(
    tmp_path,
    monkeypatch,
) -> None:
    """Disabling telemetry does not disable limits, and dormant accounts don't dilute the pool."""
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core.config import Settings
    from app.domain.reports import SourceType
    from app.main import create_app
    from app.models.telemetry import TelemetryEvent
    from app.models.user import AuthSession, User
    from app.providers.base import LLMResponse, TokenUsage
    from app.schemas.rag import EvidenceItem

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'no_telemetry_quota.db'}",
        app_environment="test",
        worker_enabled=False,
        telemetry_enabled=False,
        llm_daily_system_request_pool=2,
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    _init_app_db(app)

    with TestClient(app, headers=FRONTEND_HEADERS) as client:
        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Active", "email": "active@example.com", "password": "test-password-123"},
        )
        assert reg.status_code == 201
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "active@example.com", "password": "test-password-123"},
        ).status_code == 200

        # Seed 8 dormant accounts + 1 expired-session account that must NOT dilute active share
        with app.state.db_session_factory() as db:
            for i in range(8):
                db.add(User(name=f"Dormant{i}", email=f"dormant{i}@example.com", is_active=True))
            expired_user = User(name="Expired", email="expired@example.com", is_active=True)
            db.add(expired_user)
            db.flush()
            db.add(
                AuthSession(
                    token_hash="expired-session-hash-for-test",
                    user_id=expired_user.id,
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
                )
            )
            db.commit()

        usage = client.get("/api/v1/auth/api-keys/usage").json()
        assert usage["enrolledUsers"] == 1
        assert usage["userDailyRequestCap"] == 2

        class StubGen:
            def __init__(self) -> None:
                self.last_response: LLMResponse | None = None

            def generate(self, *_args, **_kwargs) -> str:
                self.last_response = LLMResponse(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    content="Grounded [S1].",
                    usage=TokenUsage(50, 25, 75),
                )
                return self.last_response.content

        monkeypatch.setattr(
            "app.services.rag.query.generation_service_for",
            lambda *_a, **_kw: StubGen(),
        )
        _install_retrieval_fakes(monkeypatch)

        for _ in range(2):
            assert client.post(
                "/api/v1/research/query",
                json={"query": "Run under cap without telemetry", "researchDepth": "quick"},
            ).status_code == 201

        blocked = client.post(
            "/api/v1/research/query",
            json={"query": "Should be blocked even without telemetry", "researchDepth": "quick"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "daily_model_quota_exceeded"

        final_usage = client.get("/api/v1/auth/api-keys/usage").json()
        assert final_usage["sharedRequestsUsedToday"] == 2
        assert final_usage["totalTokensToday"] == 150
        with app.state.db_session_factory() as db:
            telemetry_rows = db.execute(select(TelemetryEvent)).scalars().all()
            assert telemetry_rows == []


def test_concurrent_quota_reservations_never_exceed_cap(tmp_path) -> None:
    """Concurrent requests arriving simultaneously cannot exceed the daily quota cap."""
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    from app.core.config import Settings
    from app.db.base import Base
    from app.db.session import create_db_engine, create_session_factory
    from app.models.usage import DailyQuotaUsage
    from app.models.user import User
    from app.services.observability.usage import GLOBAL_QUOTA_SCOPE, release_shared_quota_slot

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'concurrent_quota.db'}",
        app_environment="test",
        worker_enabled=False,
        llm_daily_system_request_pool=3,
    )
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user = User(name="Burst", email="burst@example.com", is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id

    def attempt_reserve(_: int) -> bool:
        with session_factory() as thread_db:
            ok, _, _ = reserve_shared_quota_slot(
                thread_db,
                user_id=user_id,
                settings=settings,
                commit=True,
            )
            return ok

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt_reserve, range(8)))

        assert results.count(True) == 3
        assert results.count(False) == 5

        with session_factory() as db:
            rows = {
                row.scope_key: row.shared_requests_used
                for row in db.execute(select(DailyQuotaUsage)).scalars().all()
            }
            assert rows[GLOBAL_QUOTA_SCOPE] == 3
            assert rows[str(user_id)] == 3

            # Releasing unused slot decrements cleanly and never goes negative
            from datetime import datetime, timezone

            today = datetime.now(timezone.utc).date()
            release_shared_quota_slot(db, user_id=user_id, usage_date=today)
            rows_after = {
                row.scope_key: row.shared_requests_used
                for row in db.execute(select(DailyQuotaUsage)).scalars().all()
            }
            assert rows_after[GLOBAL_QUOTA_SCOPE] == 2
            assert rows_after[str(user_id)] == 2
    finally:
        engine.dispose()


def test_model_name_validation_and_gemini_url_safety(tmp_path) -> None:
    """Unsafe/traversal model names are rejected in APIs and inside GeminiAdapter."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from app.providers.base import InvalidRequestError, LLMRequest
    from app.providers.gemini import GeminiProviderAdapter

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'model_validation.db'}",
        app_environment="test",
        worker_enabled=False,
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    _init_app_db(app)

    with TestClient(app, headers=FRONTEND_HEADERS) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"name": "Val", "email": "val@example.com", "password": "test-password-123"},
        ).status_code == 201
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "val@example.com", "password": "test-password-123"},
        ).status_code == 200

        for bad_gemini in (
            "gemini-2.5-flash/../../evil",
            "gemini-2.5-flash?alt=sse",
            "gemini-2.5-flash#frag",
            "gemini/subpath",
            "gemini:colon",
            "bad model name",
        ):
            r1 = client.post(
                "/api/v1/auth/api-keys/provider-model",
                json={"provider": "gemini", "modelName": bad_gemini},
            )
            assert r1.status_code == 422, bad_gemini
            r2 = client.post(
                "/api/v1/research/query",
                json={
                    "query": "Test bad model override",
                    "preferredProvider": "gemini",
                    "modelOverride": bad_gemini,
                },
            )
            assert r2.status_code == 422, bad_gemini

        # Valid OpenRouter/Groq names containing '/' and ':' remain allowed on those providers
        assert client.post(
            "/api/v1/auth/api-keys/provider-model",
            json={"provider": "groq", "modelName": "qwen/qwen3-32b"},
        ).status_code == 200
        assert client.post(
            "/api/v1/auth/api-keys/provider-model",
            json={"provider": "openrouter", "modelName": "meta-llama/llama-3.3-70b-instruct:free"},
        ).status_code == 200

    # GeminiAdapter itself blocks URL manipulation even if constructed directly
    adapter = GeminiProviderAdapter(api_key="gemini-" + "dummy-test-key")
    import pytest as _pytest

    with _pytest.raises(InvalidRequestError):
        adapter.generate(
            LLMRequest(
                system_prompt="s",
                user_prompt="u",
                model_override="gemini-2.5-flash/../../hack",
            )
        )


def test_alembic_0016_upgrade_and_downgrade_sqlite(tmp_path, monkeypatch) -> None:
    """Verify migration 0016 upgrades cleanly and rolls back without leaving schema drift."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    db_path = tmp_path / "alembic_roundtrip.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(repo_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        try:
            insp = inspect(engine)
            tables = set(insp.get_table_names())
            assert {"user_model_preferences", "daily_quota_usage", "model_usage_daily"} <= tables
            user_cols = {c["name"] for c in insp.get_columns("users")}
            assert "local_fallback_enabled" in user_cols
            research_cols = {c["name"] for c in insp.get_columns("research")}
            assert {
                "preferred_provider",
                "model_override",
                "local_fallback_enabled",
                "allow_shared_providers",
                "shared_quota_reserved",
                "shared_quota_date",
            } <= research_cols
        finally:
            engine.dispose()

        command.downgrade(cfg, "0015_multimodal_document_enums")
        engine_down = create_engine(db_url)
        try:
            insp_down = inspect(engine_down)
            tables_down = set(insp_down.get_table_names())
            assert "daily_quota_usage" not in tables_down
            assert "model_usage_daily" not in tables_down
            assert "user_model_preferences" not in tables_down
        finally:
            engine_down.dispose()

        command.upgrade(cfg, "head")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
