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

    def fake_retrieve(session, user_id, query, settings, *, project_id=None, document_ids=None):
        return items

    monkeypatch.setattr(rag_service.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda *_args, **_kwargs: _FakeReranker())


def test_fixed_per_user_model_credits_independent_of_users_and_dual_windows(
    client: TestClient,
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    """Every user keeps fixed per-model 3-hour and 2-day credits unaffected by user count."""
    from datetime import datetime, timezone

    from app.services.observability.usage import get_user_model_usage_and_quota

    settings = test_app.state.settings
    settings.gemini_api_key = "server-gemini-key"
    settings.groq_api_key = "server-groq-key"
    settings.mistral_api_key = "server-mistral-key"
    settings.llm_router_providers = ["gemini", "groq", "mistral"]
    settings.llm_credits_3h_per_model = 2
    settings.llm_credits_2d_per_model = 4
    settings.llm_credits_short_window_hours = 3
    settings.llm_credits_long_window_days = 2
    _install_retrieval_fakes(monkeypatch)

    me = client.get("/api/v1/auth/me").json()
    user_1_id = UUID(me["id"])

    initial_usage = client.get("/api/v1/auth/api-keys/usage").json()
    assert initial_usage["overallRemainingPct"] == 100
    assert initial_usage["shortWindowHours"] == 3
    assert initial_usage["longWindowDays"] == 2
    assert initial_usage["shortCreditsPerModel"] == 2
    assert initial_usage["longCreditsPerModel"] == 4
    by_prov_1 = {item["provider"]: item for item in initial_usage["providerCredits"]}
    assert by_prov_1["gemini"]["remainingPct"] == 100
    assert by_prov_1["groq"]["remainingPct"] == 100

    # Enrolling additional users NEVER changes User 1's fixed per-model credit limits.
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

        # User 1 exhausts Gemini's 3-hour window (2 requests), yet User 2 STILL has 100% Gemini!
        with db_session_factory() as db:
            for _ in range(2):
                record_model_usage(
                    db,
                    user_id=user_1_id,
                    provider="gemini",
                    model_name="gemini-3.8-flash",
                    usage_source="shared",
                    input_tokens=100,
                    output_tokens=40,
                    increment_shared_quota=True,
                    settings=settings,
                )

        u1_usage = client.get("/api/v1/auth/api-keys/usage").json()
        u1_by_prov = {item["provider"]: item for item in u1_usage["providerCredits"]}
        assert u1_by_prov["gemini"]["remainingPct"] == 0
        assert u1_by_prov["groq"]["remainingPct"] == 100
        assert u1_by_prov["mistral"]["remainingPct"] == 100
        assert u1_usage["overallRemainingPct"] == 67

        u2_initial = client_2.get("/api/v1/auth/api-keys/usage").json()
        u2_initial_by_prov = {item["provider"]: item for item in u2_initial["providerCredits"]}
        assert u2_initial_by_prov["gemini"]["remainingPct"] == 100
        assert u2_initial_by_prov["groq"]["remainingPct"] == 100

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

        # User 2 runs 2 Gemini requests: 100% -> 50% -> 0% on Gemini, while Groq stays 100%!
        monkeypatch.setattr(
            rag_service,
            "generation_service_for",
            lambda *_args, **_kwargs: StubGenerator("gemini", "gemini-3.8-flash"),
        )
        for idx in range(2):
            ok = client_2.post(
                "/api/v1/research/query",
                json={
                    "query": f"Explain self-attention {idx}",
                    "researchDepth": "quick",
                    "preferredProvider": "gemini",
                },
            )
            assert ok.status_code == 201, ok.text

        # Direct Gemini is now blocked at 0% (429), whereas Groq is completely independent at 100%!
        blocked_gemini = client_2.post(
            "/api/v1/research/query",
            json={
                "query": "Third Gemini request blocked",
                "researchDepth": "quick",
                "preferredProvider": "gemini",
            },
        )
        assert blocked_gemini.status_code == 429
        assert blocked_gemini.json()["error"]["code"] == "daily_model_quota_exceeded"

        monkeypatch.setattr(
            rag_service,
            "generation_service_for",
            lambda *_args, **_kwargs: StubGenerator("groq", "llama-3.3-70b-versatile"),
        )
        groq_ok = client_2.post(
            "/api/v1/research/query",
            json={
                "query": "Switch to Groq while Gemini is 0%",
                "researchDepth": "quick",
                "preferredProvider": "groq",
            },
        )
        assert groq_ok.status_code == 201, groq_ok.text

        # Exhaust remaining Groq slot too -> both shared models now 0%.
        groq_ok_2 = client_2.post(
            "/api/v1/research/query",
            json={
                "query": "Second Groq request",
                "researchDepth": "quick",
                "preferredProvider": "groq",
            },
        )
        assert groq_ok_2.status_code == 201, groq_ok_2.text

        # Local Ollama and BYOK are Unlimited even when all shared models are 0%.
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

        final_usage = client_2.get("/api/v1/auth/api-keys/usage").json()
        by_prov = {item["provider"]: item for item in final_usage["providerCredits"]}
        assert by_prov["gemini"]["remainingPct"] == 0
        assert by_prov["groq"]["remainingPct"] == 0
        assert by_prov["openai"]["unlimited"] is True
        assert by_prov["openai"]["remainingPct"] == 100
        assert final_usage["byokRequestsToday"] == 1
        assert final_usage["localRequestsToday"] == 1

        # Verify 3-hour renewal replenishes short bucket while 2-day pool keeps count until 2-day reset.
        t0 = datetime(2026, 11, 18, 1, 0, tzinfo=timezone.utc)
        t1_3h = datetime(2026, 11, 18, 3, 5, tzinfo=timezone.utc)
        t2_3h_again = datetime(2026, 11, 18, 6, 5, tzinfo=timezone.utc)
        t3_2d_reset = datetime(2026, 11, 20, 0, 5, tzinfo=timezone.utc)

        with db_session_factory() as db:
            # Spend 2/2 in t0 (uses 2/2 of 3h, 2/4 of 2d -> 0% effective now).
            for _ in range(2):
                ok, _, _ = reserve_shared_quota_slot(
                    db, user_id=user_2_id, provider="mistral", settings=settings, now=t0
                )
                assert ok is True
            ok_blocked, _, _ = reserve_shared_quota_slot(
                db, user_id=user_2_id, provider="mistral", settings=settings, now=t0
            )
            assert ok_blocked is False

            # At +3h (t1): 3h window renewed (2 left -> 100%), 2-day window has 2/4 left (50%) -> 50% effective!
            snap_t1 = get_user_model_usage_and_quota(db, user_2_id, settings, now=t1_3h)
            mistral_t1 = next(i for i in snap_t1["provider_credits"] if i["provider"] == "mistral")
            assert mistral_t1["short_window_pct"] == 100
            assert mistral_t1["long_window_pct"] == 50
            assert mistral_t1["remaining_pct"] == 50

            # Spend 2 more at t1 -> 4/4 spent in 2-day window -> now blocked even after another 3h reset (t2)!
            for _ in range(2):
                ok, _, _ = reserve_shared_quota_slot(
                    db, user_id=user_2_id, provider="mistral", settings=settings, now=t1_3h
                )
                assert ok is True
            ok_2d_blocked, _, _ = reserve_shared_quota_slot(
                db, user_id=user_2_id, provider="mistral", settings=settings, now=t2_3h_again
            )
            assert ok_2d_blocked is False

            # After 2 days (t3): both windows renew to 100%!
            snap_t3 = get_user_model_usage_and_quota(db, user_2_id, settings, now=t3_2d_reset)
            mistral_t3 = next(i for i in snap_t3["provider_credits"] if i["provider"] == "mistral")
            assert mistral_t3["short_window_pct"] == 100
            assert mistral_t3["long_window_pct"] == 100
            assert mistral_t3["remaining_pct"] == 100


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
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'fake_byok_bypass.db'}",
        app_environment="test",
        worker_enabled=False,
        llm_credits_3h_per_model=1,
        llm_credits_2d_per_model=1,
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
        _env_file=None,
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
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'no_telemetry_quota.db'}",
        app_environment="test",
        worker_enabled=False,
        telemetry_enabled=False,
        llm_credits_3h_per_model=2,
        llm_credits_2d_per_model=2,
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
        assert usage["shortCreditsPerModel"] == 2
        assert usage["longCreditsPerModel"] == 2
        assert usage["overallRemainingPct"] == 100

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
        assert final_usage["overallRemainingPct"] == 0
        assert final_usage["totalTokensToday"] == 150
        with app.state.db_session_factory() as db:
            telemetry_rows = db.execute(select(TelemetryEvent)).scalars().all()
            assert telemetry_rows == []


def test_concurrent_quota_reservations_never_exceed_cap(tmp_path) -> None:
    """Concurrent requests arriving simultaneously cannot exceed the fixed 3-hour / 2-day cap."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.config import Settings
    from app.db.base import Base
    from app.db.session import create_db_engine, create_session_factory
    from app.models.usage import DailyQuotaUsage
    from app.models.user import User
    from app.services.observability.usage import release_shared_quota_slot

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'concurrent_quota.db'}",
        app_environment="test",
        worker_enabled=False,
        llm_credits_3h_per_model=3,
        llm_credits_2d_per_model=10,
    )
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user = User(name="Burst", email="burst@example.com", is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id

    fixed_now = datetime(2026, 11, 18, 4, 15, tzinfo=timezone.utc)

    def attempt_reserve(_: int) -> bool:
        with session_factory() as thread_db:
            ok, _, _ = reserve_shared_quota_slot(
                thread_db,
                user_id=user_id,
                provider="gemini",
                settings=settings,
                now=fixed_now,
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
            assert rows[f"3hq:03:gemini:{user_id.hex}"] == 12
            assert rows[f"2dq:gemini:{user_id.hex}"] == 12

            # Releasing unused slot decrements both 3h & 2d buckets cleanly and never goes negative
            release_shared_quota_slot(
                db,
                user_id=user_id,
                usage_date=fixed_now.date(),
                provider="gemini",
                short_hour=3,
                now=fixed_now,
            )
            rows_after = {
                row.scope_key: row.shared_requests_used
                for row in db.execute(select(DailyQuotaUsage)).scalars().all()
            }
            assert rows_after[f"3hq:03:gemini:{user_id.hex}"] == 8
            assert rows_after[f"2dq:gemini:{user_id.hex}"] == 8
    finally:
        engine.dispose()


def test_ungrounded_run_refunds_credit_and_fallback_transfers_attribution(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch,
) -> None:
    """Insufficient-evidence runs refund credits and failover charges only the answering model."""
    from app.providers.base import LLMProviderAdapter, LLMRequest, RateLimitError
    from app.providers.router import CentralizedLLMRouter
    from app.services.rag.generation import GenerationService

    settings = test_app.state.settings
    settings.gemini_api_key = "server-gemini-key"
    settings.groq_api_key = "server-groq-key"
    settings.mistral_api_key = "server-mistral-key"
    settings.llm_router_providers = ["gemini", "groq", "mistral"]
    settings.llm_credits_3h_per_model = 4
    settings.llm_credits_2d_per_model = 10
    _install_retrieval_fakes(monkeypatch)

    class UngroundedGenerator:
        def __init__(self) -> None:
            self.last_response: LLMResponse | None = None

        def generate(self, *_args, **_kwargs) -> str:
            self.last_response = LLMResponse(
                provider="gemini",
                model="gemini-3.8-flash",
                content="Answer without any bracketed source reference.",
                usage=TokenUsage(20, 10, 30),
            )
            return self.last_response.content

    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: UngroundedGenerator(),
    )
    ungrounded = client.post(
        "/api/v1/research/query",
        json={"query": "Ungrounded question", "researchDepth": "quick", "preferredProvider": "gemini"},
    )
    assert ungrounded.status_code == 201
    assert ungrounded.json()["insufficientEvidence"] is True

    # Because no citations passed validation, the reserved Gemini credit was refunded (100% left!).
    after_refund = client.get("/api/v1/auth/api-keys/usage").json()
    prov_refund = {i["provider"]: i for i in after_refund["providerCredits"]}
    assert prov_refund["gemini"]["remainingPct"] == 100

    # When Auto picks Gemini first, Gemini rate-limits, and Groq answers: Gemini stays 100%, Groq drops to 75%!
    class FailingGemini(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-3.8-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            raise RateLimitError("gemini", "429 busy")

    class HealthyGroq(LLMProviderAdapter):
        provider_name = "groq"
        default_model = "llama-3.3-70b-versatile"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="groq",
                model="llama-3.3-70b-versatile",
                content="Answered via failover [S1].",
                usage=TokenUsage(40, 20, 60),
            )

    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: GenerationService(
            router=CentralizedLLMRouter([FailingGemini(), HealthyGroq()], max_transient_retries=0)
        ),
    )
    failover = client.post(
        "/api/v1/research/query",
        json={"query": "Failover question", "researchDepth": "quick"},
    )
    assert failover.status_code == 201, failover.text
    after_failover = client.get("/api/v1/auth/api-keys/usage").json()
    prov_after = {i["provider"]: i for i in after_failover["providerCredits"]}
    assert prov_after["gemini"]["remainingPct"] == 100
    assert prov_after["groq"]["remainingPct"] == 75


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


def test_live_rate_limit_header_capture_and_scope_isolation() -> None:
    """Response rate-limit headers are scoped by key hash so BYOK never leaks into shared or other users."""
    import httpx

    from app.providers.base import (
        capture_rate_limit_headers,
        clear_rate_limit_snapshots,
        get_rate_limit_snapshot,
    )

    clear_rate_limit_snapshots()
    try:
        capture_rate_limit_headers(
            "groq",
            httpx.Headers(
                {
                    "x-ratelimit-limit-requests": "100",
                    "x-ratelimit-remaining-requests": "97",
                    "x-ratelimit-limit-tokens": "20000",
                    "x-ratelimit-remaining-tokens": "19250",
                    "x-ratelimit-reset-requests": "12s",
                }
            ),
            api_key="server-shared-key",
            is_byok=False,
        )
        capture_rate_limit_headers(
            "claude",
            httpx.Headers(
                {
                    "anthropic-ratelimit-requests-limit": "50",
                    "anthropic-ratelimit-requests-remaining": "49",
                    "anthropic-ratelimit-tokens-limit": "40000",
                    "anthropic-ratelimit-tokens-remaining": "39100",
                    "anthropic-ratelimit-requests-reset": "2026-11-26T00:00:00Z",
                }
            ),
            api_key="sk-ant-" + "user-a-key",
            is_byok=True,
        )

        shared_groq = get_rate_limit_snapshot("groq", api_key="server-shared-key", is_byok=False)
        assert shared_groq is not None
        assert shared_groq.limit_requests == 100
        assert shared_groq.remaining_requests == 97
        assert shared_groq.limit_tokens == 20000
        assert shared_groq.remaining_tokens == 19250
        assert shared_groq.reset_requests == "12s"
        # Same provider with BYOK scope must remain isolated.
        assert get_rate_limit_snapshot("groq", api_key="user-byok-key", is_byok=True) is None

        user_claude = get_rate_limit_snapshot("claude", api_key="sk-ant-" + "user-a-key", is_byok=True)
        assert user_claude is not None
        assert user_claude.limit_requests == 50
        assert user_claude.remaining_requests == 49
        assert user_claude.remaining_tokens == 39100
        assert get_rate_limit_snapshot("claude", api_key="sk-ant-" + "user-b-key", is_byok=True) is None
    finally:
        clear_rate_limit_snapshots()


def test_openrouter_probe_ttl_cache_and_live_usage_endpoints(
    client: TestClient,
    test_app: FastAPI,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    """?live=true merges OpenRouter /auth/key balance, response headers, and ModelUsageDaily counters."""
    import httpx

    from app.providers.base import capture_rate_limit_headers, clear_rate_limit_snapshots
    from app.services.observability import live_quota

    clear_rate_limit_snapshots()
    live_quota.clear_live_quota_cache()
    test_or_key = "sk-or-v1-" + "live-test-key-1234"
    probe_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal probe_calls
        probe_calls += 1
        assert request.url.path.endswith("/auth/key")
        assert request.headers.get("Authorization") == f"Bearer {test_or_key}"
        return httpx.Response(
            200,
            json={
                "data": {
                    "limit": 10.0,
                    "limit_remaining": 9.88,
                    "usage": 0.12,
                    "is_free_tier": False,
                    "rate_limit": {"requests": 200, "interval": "10s"},
                }
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(live_quota, "get_shared_http_client", lambda: mock_client)

    settings = test_app.state.settings
    settings.groq_api_key = "server-groq-live-key"
    settings.gemini_api_key = ""
    settings.openai_api_key = ""
    settings.openrouter_api_key = ""
    settings.llm_router_providers = ["groq"]

    try:
        # 1. Verify OpenRouter key probing caches for TTL unless force_refresh=True.
        first = live_quota.probe_openrouter_key(test_or_key, ttl_seconds=60.0)
        second = live_quota.probe_openrouter_key(test_or_key, ttl_seconds=60.0)
        assert first is not None and second is not None
        assert first.credit_limit_usd == 10.0
        assert first.credit_remaining_usd == 9.88
        assert first.credit_usage_usd == 0.12
        assert first.limit_requests == 200
        assert probe_calls == 1

        forced = live_quota.probe_openrouter_key(
            test_or_key,
            ttl_seconds=60.0,
            force_refresh=True,
        )
        assert forced is not None and forced.credit_remaining_usd == 9.88
        assert probe_calls == 2

        # 2. Save user BYOK OpenRouter key + record daily model usage + capture shared Groq headers.
        assert client.put(
            "/api/v1/auth/api-keys/openrouter",
            json={"apiKey": test_or_key},
        ).status_code == 200

        me = client.get("/api/v1/auth/me").json()
        user_id = UUID(me["id"])
        with db_session_factory() as db:
            for _ in range(3):
                record_model_usage(
                    db,
                    user_id=user_id,
                    provider="openrouter",
                    model_name="openrouter/free",
                    usage_source="byok",
                    input_tokens=300,
                    output_tokens=150,
                    increment_shared_quota=False,
                    settings=settings,
                )
            record_model_usage(
                db,
                user_id=user_id,
                provider="groq",
                model_name="llama-3.3-70b-versatile",
                usage_source="shared",
                input_tokens=200,
                output_tokens=100,
                increment_shared_quota=True,
                settings=settings,
            )

        capture_rate_limit_headers(
            "groq",
            httpx.Headers(
                {
                    "x-ratelimit-limit-requests": "100",
                    "x-ratelimit-remaining-requests": "98",
                    "x-ratelimit-limit-tokens": "20000",
                    "x-ratelimit-remaining-tokens": "19800",
                }
            ),
            api_key="server-groq-live-key",
            is_byok=False,
        )

        # 3. Call /usage?live=true and /models-status?live=true and verify merged real telemetry.
        usage_resp = client.get("/api/v1/auth/api-keys/usage?live=true")
        assert usage_resp.status_code == 200, usage_resp.text
        usage_data = usage_resp.json()
        by_prov = {item["provider"]: item for item in usage_data["providerCredits"]}

        or_item = by_prov["openrouter"]
        assert or_item["mode"] == "byok"
        assert or_item["liveSource"] == "provider_api"
        assert or_item["liveCreditRemainingUsd"] == 9.88
        assert or_item["liveCreditLimitUsd"] == 10.0
        assert or_item["requestsToday"] == 3
        assert or_item["tokensToday"] == 1350

        groq_item = by_prov["groq"]
        assert groq_item["mode"] == "shared"
        assert groq_item["liveSource"] == "response_headers"
        assert groq_item["liveLimitRequests"] == 100
        assert groq_item["liveRemainingRequests"] == 98
        assert groq_item["liveLimitTokens"] == 20000
        assert groq_item["liveRemainingTokens"] == 19800
        assert groq_item["requestsToday"] == 1
        assert groq_item["tokensToday"] == 300

        models_resp = client.get("/api/v1/auth/api-keys/models-status?live=true")
        assert models_resp.status_code == 200, models_resp.text
        models_credits = {
            item["provider"]: item for item in models_resp.json()["usage"]["providerCredits"]
        }
        assert models_credits["openrouter"]["liveSource"] == "provider_api"
        assert models_credits["openrouter"]["liveCreditRemainingUsd"] == 9.88
        assert models_credits["groq"]["liveSource"] == "response_headers"
    finally:
        mock_client.close()
        live_quota.clear_live_quota_cache()
        clear_rate_limit_snapshots()
