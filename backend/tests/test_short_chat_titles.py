"""Tests for <= 3-word chat title generation, sanitization, and legacy backfill."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.report import ResearchReport
from app.models.research import Research
from app.providers.base import (
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ProviderOutageError,
    TokenUsage,
)
from app.providers.router import CentralizedLLMRouter
from app.services.rag import query as rag_service
from app.services.rag.generation import GenerationService
from app.services.research.titles import (
    MAX_CHAT_TITLE_WORDS,
    backfill_legacy_research_titles,
    build_fallback_title,
    legacy_fallback_title,
    normalize_short_title,
)
from test_rag_api import candidates, install_pipeline_fakes


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How do citations support claims?", "Citations Support Claims"),
        ("What is market research?", "Market Research"),
        (
            "How do transformers handle long context windows in recent LLM architectures?",
            "Transformers Long Context",
        ),
        (
            "Can you please explain how hybrid RAG retrieval works?",
            "Hybrid RAG Retrieval",
        ),
        ("Compare PostgreSQL vs SQLite for search", "PostgreSQL vs SQLite"),
        ("What are the side effects of lithium carbonate?", "Side Effects Lithium"),
        ("Anything at all?", "Anything"),
        ("   ???   ", "New Research"),
        ("WHAT IS POSTGRESQL FTS?", "Postgresql Fts"),
    ],
)
def test_build_fallback_title_caps_at_three_words(question: str, expected: str) -> None:
    result = build_fallback_title(question)
    assert 1 <= len(result.split()) <= MAX_CHAT_TITLE_WORDS
    assert result == expected


def test_build_fallback_title_always_bounds_words_and_length() -> None:
    very_long_word = "supercalifragilisticexpialidocious" * 4
    single = build_fallback_title(very_long_word)
    assert len(single.split()) == 1
    assert len(single) <= 80


@pytest.mark.parametrize(
    ("raw", "question", "expected"),
    [
        ("Transformer Context Windows", "How do transformers handle long context windows?", "Transformer Context Windows"),
        ("Title: \"Lithium Side Effects.\"", "What are side effects of lithium?", "Lithium Side Effects"),
        ("<think>thinking...</think>\nCool Roof Temperatures!", "Do cool roofs cool?", "Cool Roof Temperatures"),
        ("<think>truncated thinking without answer", "What is market research?", "Market Research"),
        ("1. Overview of Hybrid RAG Retrieval Performance", "Explain hybrid RAG retrieval", "Hybrid RAG Retrieval"),
        ("   ", "What is market research?", "Market Research"),
    ],
)
def test_normalize_short_title_handles_llm_noise(
    raw: str,
    question: str,
    expected: str,
) -> None:
    result = normalize_short_title(raw, fallback_question=question)
    assert 1 <= len(result.split()) <= MAX_CHAT_TITLE_WORDS
    assert result == expected


def test_generation_service_generate_short_title_router_and_resilience() -> None:
    seen_requests: list[LLMRequest] = []

    class StubAdapter(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-3.8-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            seen_requests.append(request)
            return LLMResponse(
                provider="gemini",
                model="gemini-3.8-flash",
                content="Transformer Context Windows",
                usage=TokenUsage(12, 4, 16),
            )

    service = GenerationService(router=CentralizedLLMRouter([StubAdapter()]))
    service.last_response = LLMResponse(
        provider="gemini",
        model="gemini-3.8-flash",
        content="Grounded [S1].",
        usage=TokenUsage(50, 20, 70),
    )

    short = service.generate_short_title(
        "How do transformers handle long context windows?",
        preferred_provider="gemini",
    )
    assert short == "Transformer Context Windows"
    assert len(seen_requests) == 1
    assert seen_requests[0].max_tokens == 20
    # Must preserve last_response for main RAG answer accounting.
    assert service.last_response.content == "Grounded [S1]."

    class BrokenAdapter(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-3.8-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            raise ProviderOutageError("gemini", "temporary outage")

    broken = GenerationService(router=CentralizedLLMRouter([BrokenAdapter()], max_transient_retries=0))
    assert broken.generate_short_title("What is market research?") is None


def test_generation_service_generate_short_title_direct_ollama() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        if request.url.path == "/api/generate":
            return httpx.Response(
                200,
                json={"response": "Neon Hybrid Retrieval"},
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama.test")
    service = GenerationService(base_url="http://ollama.test", model_name="qwen3.5:9b", client=client)
    service._verify_model()
    assert service.generate_short_title("How does Neon hybrid retrieval work?") == "Neon Hybrid Retrieval"


def test_execute_research_uses_llm_short_title_when_enabled_and_respects_custom_titles(
    client: TestClient,
    test_app,
    db_session: Session,
    monkeypatch,
) -> None:
    install_pipeline_fakes(monkeypatch, candidates())

    class TitleAdapter(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-3.8-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            if "1 to 3 word" in request.system_prompt:
                return LLMResponse(
                    provider="gemini",
                    model="gemini-3.8-flash",
                    content='"Evidence Impact Summary"',
                    usage=TokenUsage(15, 5, 20),
                )
            return LLMResponse(
                provider="gemini",
                model="gemini-3.8-flash",
                content="The studies report measurable improvement [S1] [S2].",
                usage=TokenUsage(100, 20, 120),
            )

    test_app.state.settings.chat_title_llm_enabled = True
    test_app.state.settings.gemini_api_key = "test-gemini-key"
    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([TitleAdapter()])),
    )

    response = client.post(
        "/api/v1/research/query",
        json={
            "query": "What are the long term effects of this intervention across the uploaded papers?",
            "researchDepth": "quick",
        },
    )
    assert response.status_code == 201, response.text
    research_id = UUID(response.json()["researchId"])

    detail = client.get(f"/api/v1/research/{research_id}").json()
    assert detail["title"] == "Evidence Impact Summary"
    assert len(detail["title"].split()) <= 3

    report = client.get(f"/api/v1/research/{research_id}/report").json()
    assert report["report"]["title"] == "Evidence Impact Summary"
    assert report["report"]["question"] == "What are the long term effects of this intervention across the uploaded papers?"

    # Custom user rename must never be overwritten when a queued/retried run completes.
    custom = client.post(
        "/api/v1/research",
        json={"question": "How do citations support claims?", "title": "My Custom Name"},
    ).json()
    custom_id = UUID(custom["id"])
    assert custom["title"] == "My Custom Name"
    from app.services.research import runs as research_runs

    research_runs.start_research(db_session, custom_id)
    rag_service.execute_research(
        db_session,
        custom_id,
        UUID(client.get("/api/v1/auth/me").json()["id"]),
        test_app.state.settings,
    )
    assert client.get(f"/api/v1/research/{custom_id}").json()["title"] == "My Custom Name"


def test_backfill_legacy_research_titles_shortens_only_legacy_auto_titles_and_preserves_timestamps(
    client: TestClient,
    db_session: Session,
) -> None:
    old_time = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    legacy_question = "How do transformers handle long context windows in recent LLM architectures?"
    legacy_title = legacy_fallback_title(legacy_question)

    legacy = client.post(
        "/api/v1/research",
        json={"question": legacy_question, "title": legacy_title},
    ).json()
    custom = client.post(
        "/api/v1/research",
        json={
            "question": "What are the side effects of lithium carbonate on renal function?",
            "title": "My Custom Four Word Title",
        },
    ).json()

    legacy_id = UUID(legacy["id"])
    custom_id = UUID(custom["id"])

    # Seed matching report and old timestamp on the legacy record.
    legacy_rec = db_session.get(Research, legacy_id)
    assert legacy_rec is not None
    legacy_rec.updated_at = old_time
    report = ResearchReport(
        research_id=legacy_id,
        title=legacy_title,
        summary="Summary",
        dossier_ref="LOCAL RAG · TEST",
        reading_time_minutes=1,
        version=1,
    )
    db_session.add(report)
    db_session.commit()

    count = backfill_legacy_research_titles(db_session)
    assert count == 1

    db_session.expire_all()
    refreshed_legacy = db_session.get(Research, legacy_id)
    refreshed_report = db_session.get(ResearchReport, report.id)
    refreshed_custom = db_session.get(Research, custom_id)

    assert refreshed_legacy is not None
    assert refreshed_legacy.title == "Transformers Long Context"
    assert len(refreshed_legacy.title.split()) <= 3
    assert refreshed_legacy.updated_at == old_time
    assert refreshed_report is not None
    assert refreshed_report.title == "Transformers Long Context"
    assert refreshed_custom is not None
    assert refreshed_custom.title == "My Custom Four Word Title"
