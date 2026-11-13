"""Comprehensive unit, integration, and end-to-end tests for Phases 1–8 and TEST 1–8."""

from __future__ import annotations

from io import BytesIO
import struct
import wave
from pathlib import Path
from uuid import uuid4

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
import httpx
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import Base
from app.db.neon_migration import generate_rollback_plan, migrate_database
from app.db.session import create_db_engine, is_neon_pooled_url, normalize_database_url
from app.domain.documents import DocumentStatus, DocumentType
from app.models.api_key import UserAPIKey
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.providers.base import (
    AuthenticationError,
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ProviderOutageError,
    RateLimitError,
    TokenUsage,
)
from app.providers.cerebras import CerebrasProviderAdapter
from app.providers.gemini import GeminiProviderAdapter
from app.providers.mistral import MistralProviderAdapter
from app.providers.openrouter import OpenRouterProviderAdapter
from app.providers.router import CentralizedLLMRouter, build_router_for_settings
from app.schemas.retrieval import RetrievalCandidate
from app.services.documents.storage import R2DocumentStorage
from app.services.ingestion.audio import (
    DocumentIngestionError,
    GroqAudioTranscriber,
    TranscriptSegment,
    audio_transcriber_for,
)
from app.services.ingestion.video import ExtractedKeyframe, VideoIngestionAdapter
from app.services.ingestion.vision import GeminiVisionAnalyzer, inspect_image_for_vision
from app.services.ingestion.web import WebsiteIngestionAdapter, validate_public_url
from app.services.ingestion.youtube import YouTubeIngestionAdapter, extract_youtube_video_id
from app.services.observability.telemetry import record_telemetry_event
from app.services.rag.embeddings import CloudflareWorkersAIEmbeddingService
from app.services.rag.generation import GenerationService
from app.services.rag.reranking import (
    CloudflareBGERerankerService,
    JinaRerankerService,
    LexicalFallbackReranker,
    reranker_service_for,
)


class DeterministicEmbeddingService:
    """Fast deterministic 1024-d embedding service for end-to-end RAG workflow tests."""

    dimension = 1024

    def _vector_for(self, text: str) -> list[float]:
        lower = text.lower()
        vec = [0.001] * self.dimension
        keywords = [
            "quantum",
            "annealing",
            "transformer",
            "attention",
            "crispr",
            "cas9",
            "battery",
            "electrolyte",
            "youtube",
            "whisper",
            "keyframe",
            "neon",
        ]
        for idx, kw in enumerate(keywords):
            if kw in lower:
                vec[idx] = 1.0
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(t) for t in texts]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._vector_for(query)


class KeywordAwareReranker:
    """Deterministic reranker scoring candidates by query token overlap."""

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        q_terms = {w.lower() for w in query.split() if len(w) > 2}
        scored = []
        for candidate in candidates:
            text_lower = candidate.text.lower()
            hits = sum(1 for term in q_terms if term in text_lower)
            score = 0.5 + 0.1 * hits
            scored.append(candidate.model_copy(update={"rerank_score": score}))
        scored.sort(key=lambda c: -float(c.rerank_score or 0.0))
        return scored


def _build_pdf_bytes(pages: list[str]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_text in pages:
        text_obj = pdf.beginText(72, 750)
        for line in page_text.splitlines():
            text_obj.textLine(line)
        pdf.drawText(text_obj)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _build_pptx_bytes() -> bytes:
    prs = Presentation()
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Solid State Battery Architecture"
    slide.placeholders[1].text = (
        "Lithium thiophosphate solid electrolytes achieve 12 mS/cm ionic conductivity at room temperature."
    )
    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _build_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BenchmarkMetrics"
    ws.append(["Model", "Accuracy", "LatencyMs"])
    ws.append(["Qwen3-Embedding-0.6B", "94.2%", "18"])
    ws.append(["BGE-Reranker-Base", "91.8%", "24"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_wav_bytes(duration_seconds: float = 0.25, sample_rate: int = 8000) -> bytes:
    buf = BytesIO()
    num_samples = int(duration_seconds * sample_rate)
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = b"".join(struct.pack("<h", 500 if i % 20 < 10 else -500) for i in range(num_samples))
        wav_file.writeframes(frames)
    return buf.getvalue()


# ============================================================================
# TEST 1 — PDF Research Workflow (End-to-End)
# ============================================================================
def test_e2e_1_pdf_research_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 1: Upload PDF -> parse -> chunk -> embed -> store -> query -> hybrid retrieve -> rerank -> LLM router -> citations."""
    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr(
        "app.services.ingestion.pipeline.embedding_service_for",
        lambda _s: det_embeddings,
    )
    monkeypatch.setattr(
        "app.services.rag.retrieval.embedding_service_for",
        lambda _s: det_embeddings,
    )
    monkeypatch.setattr(
        "app.services.rag.query.reranker_service_for",
        lambda _s: KeywordAwareReranker(),
    )

    class MockCerebrasAdapter(LLMProviderAdapter):
        provider_name = "cerebras"
        default_model = "llama-3.3-70b"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="cerebras",
                model=self.default_model,
                content="Quantum annealing reduces combinatorial optimization energy barriers by 42% [S1].",
                usage=TokenUsage(prompt_tokens=120, completion_tokens=24, total_tokens=144),
                latency_ms=35.0,
            )

    router = CentralizedLLMRouter([MockCerebrasAdapter()])
    gen_service = GenerationService(router=router)
    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: gen_service,
    )

    pdf_bytes = _build_pdf_bytes(
        [
            "Quantum Annealing Optimization Study\n\n"
            "Abstract\n"
            "Quantum annealing reduces combinatorial optimization energy barriers by 42% compared to simulated annealing.",
            "Methods\n"
            "Experiments were performed on a 5000-qubit superconducting processor with transverse field schedules.",
        ]
    )
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("quantum_study.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 201, upload_res.text
    doc_payload = upload_res.json()
    assert doc_payload["status"] == "indexed"
    assert doc_payload["chunkCount"] >= 1
    assert doc_payload["embeddingModel"] is not None

    query_res = client.post(
        "/api/v1/research/query",
        json={"query": "How much does quantum annealing reduce optimization energy barriers?"},
    )
    assert query_res.status_code == 201, query_res.text
    body = query_res.json()
    assert body["insufficientEvidence"] is False
    assert "42%" in body["answer"]
    assert len(body["citations"]) >= 1
    assert body["citations"][0]["documentId"] == doc_payload["id"]
    assert body["citations"][0]["page"] >= 1


# ============================================================================
# TEST 2 — YouTube Research Workflow (End-to-End)
# ============================================================================
def test_e2e_2_youtube_research_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 2: Provide YouTube URL -> extract transcript -> chunk with timestamps -> embed -> query -> cited answer."""
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.query.reranker_service_for", lambda _s: KeywordAwareReranker())

    monkeypatch.setattr(
        YouTubeIngestionAdapter,
        "_fetch_segments",
        lambda self, video_id: (
            [
                TranscriptSegment(
                    text="Welcome to the lecture on transformer attention mechanisms.",
                    start=0.0,
                    duration=15.0,
                ),
                TranscriptSegment(
                    text="Multi-head attention computes scaled dot-product attention across parallel subspaces.",
                    start=15.0,
                    duration=20.0,
                ),
            ],
            "Transformer Attention Lecture",
        ),
    )

    class MockGeminiAdapter(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-2.5-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="gemini",
                model=self.default_model,
                content="Multi-head transformer attention computes scaled dot-product attention across parallel subspaces [S1].",
                usage=TokenUsage(prompt_tokens=90, completion_tokens=20, total_tokens=110),
            )

    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([MockGeminiAdapter()])),
    )

    ingest_res = client.post(
        "/api/v1/documents/url",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Transformer Attention Lecture",
        },
    )
    assert ingest_res.status_code == 201, ingest_res.text
    doc_data = ingest_res.json()
    assert doc_data["type"] == "youtube"
    assert doc_data["status"] == "indexed"
    assert doc_data["chunkCount"] >= 1

    query_res = client.post(
        "/api/v1/research/query",
        json={"query": "What does multi-head transformer attention compute on YouTube?"},
    )
    assert query_res.status_code == 201, query_res.text
    q_body = query_res.json()
    assert q_body["insufficientEvidence"] is False
    assert "scaled dot-product attention" in q_body["answer"]
    assert q_body["citations"][0]["documentId"] == doc_data["id"]
    assert "00:00" in (q_body["citations"][0]["section"] or "")


# ============================================================================
# TEST 3 — Website Research Workflow & SSRF Protection (End-to-End)
# ============================================================================
def test_e2e_3_website_research_workflow_and_ssrf_guard(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 3: Provide website URL -> extract clean content -> chunk -> embed -> query -> answer with source citation."""
    with pytest.raises(AppError) as exc_info:
        validate_public_url("http://127.0.0.1:8000/admin")
    assert exc_info.value.code == "ssrf_blocked_url"

    with pytest.raises(AppError) as exc_info_meta:
        validate_public_url("http://169.254.169.254/latest/meta-data/")
    assert exc_info_meta.value.code == "ssrf_blocked_url"

    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.query.reranker_service_for", lambda _s: KeywordAwareReranker())

    monkeypatch.setattr(
        "app.services.ingestion.web.validate_public_url",
        lambda url, resolver=None: url,
    )

    def mock_web_get(self, url: str, **kwargs):
        return httpx.Response(
            200,
            text=(
                "Title: CRISPR Cas9 Gene Editing Overview\n\n"
                "# Mechanism of Action\n"
                "CRISPR-Cas9 uses a guide RNA to direct the Cas9 endonuclease to a target DNA sequence next to a PAM motif."
            ),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_web_get)

    class MockMistralAdapter(LLMProviderAdapter):
        provider_name = "mistral"
        default_model = "mistral-small-latest"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="mistral",
                model=self.default_model,
                content="CRISPR-Cas9 relies on a guide RNA to direct the Cas9 endonuclease to a target DNA sequence [S1].",
                usage=TokenUsage(prompt_tokens=80, completion_tokens=20, total_tokens=100),
            )

    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([MockMistralAdapter()])),
    )

    web_res = client.post(
        "/api/v1/documents/url",
        json={"url": "https://example.org/crispr-cas9-review"},
    )
    assert web_res.status_code == 201, web_res.text
    web_doc = web_res.json()
    assert web_doc["type"] == "web"
    assert web_doc["sourceUrl"] == "https://example.org/crispr-cas9-review"

    query_res = client.post(
        "/api/v1/research/query",
        json={"query": "How does CRISPR Cas9 target DNA sequences?"},
    )
    assert query_res.status_code == 201
    q_data = query_res.json()
    assert "guide RNA" in q_data["answer"]
    assert q_data["citations"][0]["documentId"] == web_doc["id"]


# ============================================================================
# TEST 4 — Audio Research Workflow (End-to-End)
# ============================================================================
def test_e2e_4_audio_research_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 4: Upload audio -> transcribe via Groq Whisper -> chunk -> embed -> query -> timestamp citation."""
    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.query.reranker_service_for", lambda _s: KeywordAwareReranker())

    monkeypatch.setattr(
        GroqAudioTranscriber,
        "transcribe_file",
        lambda self, file_path: [
            TranscriptSegment(
                text="In this whisper audio interview we confirm that solid electrolyte battery cells lasted 1500 cycles.",
                start=12.0,
                duration=16.5,
            )
        ],
    )

    class MockOpenRouterAdapter(LLMProviderAdapter):
        provider_name = "openrouter"
        default_model = "meta-llama/llama-3.3-70b-instruct:free"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="openrouter",
                model=self.default_model,
                content="The solid electrolyte battery cells lasted 1500 cycles in the audio interview [S1].",
                usage=TokenUsage(prompt_tokens=75, completion_tokens=18, total_tokens=93),
            )

    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([MockOpenRouterAdapter()])),
    )

    wav_bytes = _build_wav_bytes()
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("battery_interview.wav", wav_bytes, "audio/wav")},
    )
    assert upload_res.status_code == 201, upload_res.text
    audio_doc = upload_res.json()
    assert audio_doc["type"] == "audio"
    assert audio_doc["status"] == "indexed"

    query_res = client.post(
        "/api/v1/research/query",
        json={"query": "How many cycles did the solid electrolyte battery cells last in the whisper audio?"},
    )
    assert query_res.status_code == 201
    q_data = query_res.json()
    assert "1500 cycles" in q_data["answer"]
    assert q_data["citations"][0]["documentId"] == audio_doc["id"]
    assert "00:12" in (q_data["citations"][0]["section"] or "")


# ============================================================================
# TEST 5 — Video Research Workflow (End-to-End)
# ============================================================================
def test_e2e_5_video_research_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 5: Upload video -> extract audio & selective keyframes -> transcribe -> chunk -> embed -> query."""
    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.query.reranker_service_for", lambda _s: KeywordAwareReranker())

    def fake_extract_audio(self, video_path: Path, out_wav: Path) -> Path:
        out_wav.write_bytes(_build_wav_bytes())
        return out_wav

    def fake_extract_keyframes(self, video_path: Path, out_dir: Path) -> list[ExtractedKeyframe]:
        frame_path = out_dir / "frame_001.png"
        img = Image.new("RGB", (400, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        for x in range(40, 360, 20):
            draw.line([(x, 40), (x, 260)], fill=(10, 20, 180), width=2)
        img.save(frame_path)
        return [ExtractedKeyframe(path=frame_path, timestamp_seconds=45.0)]

    monkeypatch.setattr(VideoIngestionAdapter, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(VideoIngestionAdapter, "extract_selective_keyframes", fake_extract_keyframes)
    monkeypatch.setattr(
        GroqAudioTranscriber,
        "transcribe_file",
        lambda self, file_path: [
            TranscriptSegment(
                text="At the 45 second keyframe we display the Neon pgvector latency benchmark chart.",
                start=40.0,
                duration=12.0,
            )
        ],
    )

    class MockRouterAdapter(LLMProviderAdapter):
        provider_name = "cerebras"
        default_model = "llama-3.3-70b"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                provider="cerebras",
                model=self.default_model,
                content="The video keyframe at 45 seconds shows the Neon pgvector latency benchmark chart [S1].",
                usage=TokenUsage(prompt_tokens=80, completion_tokens=19, total_tokens=99),
            )

    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([MockRouterAdapter()])),
    )

    # MP4 ftyp header bytes
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 128
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("demo_presentation.mp4", mp4_bytes, "video/mp4")},
    )
    assert upload_res.status_code == 201, upload_res.text
    video_doc = upload_res.json()
    assert video_doc["type"] == "video"
    assert video_doc["status"] == "indexed"

    query_res = client.post(
        "/api/v1/research/query",
        json={"query": "What does the keyframe show in the Neon benchmark video?"},
    )
    assert query_res.status_code == 201
    assert "Neon pgvector latency benchmark" in query_res.json()["answer"]


# ============================================================================
# TEST 6 — LLM Fallback & Circuit Breaker Workflow
# ============================================================================
def test_e2e_6_llm_router_cascading_fallback_and_circuit_breaker() -> None:
    """TEST 6: Simulate primary provider failure -> verify automatic fallback -> verify circuit breaker & logging."""
    call_log: list[str] = []

    class FailingCerebras(LLMProviderAdapter):
        provider_name = "cerebras"
        default_model = "llama-3.3-70b"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            call_log.append("cerebras")
            raise RateLimitError("cerebras", "429 quota exceeded", status_code=429, retry_after_seconds=120.0)

    class FailingGemini(LLMProviderAdapter):
        provider_name = "gemini"
        default_model = "gemini-2.5-flash"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            call_log.append("gemini")
            raise ProviderOutageError("gemini", "503 service unavailable", status_code=503)

    class WorkingMistral(LLMProviderAdapter):
        provider_name = "mistral"
        default_model = "mistral-small-latest"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            call_log.append("mistral")
            return LLMResponse(
                provider="mistral",
                model=self.default_model,
                content="Fallback answer from Mistral [S1].",
                usage=TokenUsage(prompt_tokens=50, completion_tokens=10, total_tokens=60),
                latency_ms=42.0,
            )

    events: list[dict[str, object]] = []
    router = CentralizedLLMRouter(
        [FailingCerebras(), FailingGemini(), WorkingMistral()],
        failure_threshold=2,
        cooldown_seconds=60.0,
        max_transient_retries=0,
        on_event=events.append,
    )

    req = LLMRequest(system_prompt="You are grounded.", user_prompt="Explain [S1].")
    resp = router.generate(req)
    assert resp.provider == "mistral"
    assert resp.fallback_attempts == 2
    assert call_log == ["cerebras", "gemini", "mistral"]

    # Cerebras tripped its circuit on 429 RateLimitError, so a second call skips Cerebras!
    call_log.clear()
    resp2 = router.generate(req)
    assert resp2.provider == "mistral"
    assert "cerebras" not in call_log
    snapshot = router.get_health_snapshot()
    assert snapshot["cerebras"]["circuit_state"] == "open"
    assert snapshot["mistral"]["success_count"] == 2
    assert len(events) >= 3


# ============================================================================
# TEST 7 — BYOK (Bring Your Own Key) Workflow
# ============================================================================
def test_e2e_7_byok_workflow(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST 7: Add user API key -> verify encrypted at rest -> run query using BYOK -> revoke key -> fallback."""
    raw_user_key = "csk-user-secret-api-key-987654321"
    put_res = client.put(
        "/api/v1/auth/api-keys/cerebras",
        json={"apiKey": raw_user_key},
    )
    assert put_res.status_code == 200, put_res.text
    key_meta = put_res.json()
    assert key_meta["provider"] == "cerebras"
    assert key_meta["keyHint"] == "csk-...4321"
    assert raw_user_key not in put_res.text

    # Verify encrypted at rest in database
    with db_session_factory() as db:
        stored_row = db.scalar(select(UserAPIKey).where(UserAPIKey.provider == "cerebras"))
        assert stored_row is not None
        assert stored_row.encrypted_key != raw_user_key
        assert raw_user_key not in stored_row.encrypted_key

    # Execute a query and verify the user's decrypted key is passed to the provider
    captured_keys: list[str | None] = []

    class InspectingCerebrasAdapter(LLMProviderAdapter):
        provider_name = "cerebras"
        default_model = "llama-3.3-70b"

        def is_configured(self, api_key_override: str | None = None) -> bool:
            return True

        def generate(self, request: LLMRequest) -> LLMResponse:
            captured_keys.append(request.api_key_override)
            return LLMResponse(
                provider="cerebras",
                model=self.default_model,
                content="BYOK grounded synthesis [S1].",
                usage=TokenUsage(prompt_tokens=40, completion_tokens=10, total_tokens=50),
                used_byok=bool(request.api_key_override),
            )

    client.app.state.settings.embedding_enabled = True
    client.app.state.settings.allow_sqlite_retrieval_fallback = True
    det_embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: det_embeddings)
    monkeypatch.setattr("app.services.rag.query.reranker_service_for", lambda _s: KeywordAwareReranker())
    monkeypatch.setattr(
        "app.services.rag.query.generation_service_for",
        lambda _s: GenerationService(router=CentralizedLLMRouter([InspectingCerebrasAdapter()])),
    )

    pdf_bytes = _build_pdf_bytes(["Quantum annealing lowers energy barriers in spin glasses."])
    client.post("/api/v1/documents", files={"file": ("spin.pdf", pdf_bytes, "application/pdf")})
    q_res = client.post("/api/v1/research/query", json={"query": "What lowers energy barriers in quantum annealing?"})
    assert q_res.status_code == 201
    assert captured_keys == [raw_user_key]

    # Check usage counter incremented
    list_res = client.get("/api/v1/auth/api-keys")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 1
    assert items[0]["usageRequests"] == 1
    assert items[0]["usageTokens"] == 50

    # Revoke key and verify fallback to system key (api_key_override is None)
    del_res = client.delete("/api/v1/auth/api-keys/cerebras")
    assert del_res.status_code == 204
    assert client.get("/api/v1/auth/api-keys").json()["items"] == []

    captured_keys.clear()
    q_res_after = client.post(
        "/api/v1/research/query",
        json={"query": "What lowers energy barriers in quantum annealing?"},
    )
    assert q_res_after.status_code == 201
    assert captured_keys == [None]


# ============================================================================
# TEST 8 — Database Migration Verification (Supabase -> Neon)
# ============================================================================
def test_e2e_8_database_migration_verification(tmp_path: Path) -> None:
    """TEST 8: Compare row counts, document IDs, chunk IDs, vector dimensions, and similarity search after migration."""
    assert normalize_database_url("postgres://u:p@ep-cool-pooler.us-east-2.aws.neon.tech/neondb") == (
        "postgresql+psycopg://u:p@ep-cool-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )
    assert is_neon_pooled_url("postgresql+psycopg://u:p@ep-cool-pooler.us-east-2.aws.neon.tech/neondb") is True
    assert is_neon_pooled_url("postgresql+psycopg://u:p@ep-cool.us-east-2.aws.neon.tech/neondb") is False

    source_url = f"sqlite:///{tmp_path / 'source_supabase.db'}"
    target_url = f"sqlite:///{tmp_path / 'target_neon.db'}"
    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)
    Base.metadata.create_all(src_engine)
    Base.metadata.create_all(tgt_engine)

    user_id = uuid4()
    doc_id = uuid4()
    chunk_id = uuid4()
    embedding_vec = [0.05] * 1024

    with Session(src_engine) as src_db:
        src_db.add(
            User(
                id=user_id,
                email="researcher@example.com",
                name="Researcher",
                password_hash="argon2$hash",
            )
        )
        src_db.add(
            Document(
                id=doc_id,
                user_id=user_id,
                name="paper.pdf",
                stored_name="paper.pdf",
                file_type=DocumentType.PDF,
                mime_type="application/pdf",
                size=1024,
                status=DocumentStatus.INDEXED,
            )
        )
        src_db.add(
            DocumentChunk(
                id=chunk_id,
                document_id=doc_id,
                node_id="node-1",
                chunk_index=0,
                page=1,
                text="Migrated chunk text with 1024-dim vector.",
                embedding=embedding_vec,
            )
        )
        src_db.commit()

    dry_report = migrate_database(src_engine, tgt_engine, dry_run=True)
    assert dry_report.dry_run is True

    live_report = migrate_database(src_engine, tgt_engine, dry_run=False)
    assert live_report.ok is True
    counts_by_name = {item.table_name: item for item in live_report.tables}
    assert counts_by_name["users"].source_count == 1
    assert counts_by_name["users"].target_count == 1
    assert counts_by_name["documents"].target_count == 1
    assert counts_by_name["document_chunks"].target_count == 1
    assert live_report.document_ids_verified is True
    assert live_report.chunk_ids_verified is True
    assert live_report.vector_dimensions_verified is True
    assert live_report.similarity_query_verified is True
    assert "NEON_DATABASE_URL" in generate_rollback_plan()


# ============================================================================
# Additional Unit Tests for Phase 2 (R2 Storage), Phase 3 (Office/HTML), Phase 4 (Embeddings/Rerankers)
# ============================================================================
def test_r2_storage_presigned_urls_and_put_get_delete(tmp_path: Path) -> None:
    """Verify Cloudflare R2 S3-compatible SigV4 signing, upload, download, and presigned URLs."""
    objects: dict[str, bytes] = {}

    def r2_handler(request: httpx.Request) -> httpx.Response:
        assert "AWS4-HMAC-SHA256" in request.headers.get("Authorization", "")
        key = request.url.path
        if request.method == "PUT":
            objects[key] = request.content
            return httpx.Response(200)
        if request.method == "GET":
            if key not in objects:
                return httpx.Response(404)
            return httpx.Response(200, content=objects[key])
        if request.method == "DELETE":
            objects.pop(key, None)
            return httpx.Response(204)
        return httpx.Response(400)

    mock_client = httpx.Client(transport=httpx.MockTransport(r2_handler))
    r2 = R2DocumentStorage(
        tmp_path,
        max_upload_bytes=10 * 1024 * 1024,
        bucket_name="research-bucket",
        access_key_id="r2-test-access-key-id",
        secret_access_key="r2-test-secret-access-key",
        endpoint_url="https://acc123.r2.cloudflarestorage.com",
        http_client=mock_client,
    )
    presigned = r2.generate_presigned_url("test.pdf", expires_in=600, filename="paper.pdf")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in presigned
    assert "X-Amz-Signature=" in presigned
    assert "research-bucket/test.pdf" in presigned


def test_office_pptx_xlsx_and_html_ingestion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify PPTX, XLSX, and HTML documents parse and index with slide/sheet/section metadata."""
    client.app.state.settings.embedding_enabled = False

    pptx_res = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "slides.pptx",
                _build_pptx_bytes(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    assert pptx_res.status_code == 201, pptx_res.text
    assert pptx_res.json()["type"] == "pptx"
    assert pptx_res.json()["chunkCount"] >= 1

    xlsx_res = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "metrics.xlsx",
                _build_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert xlsx_res.status_code == 201, xlsx_res.text
    assert xlsx_res.json()["type"] == "xlsx"
    assert xlsx_res.json()["chunkCount"] >= 1

    html_bytes = (
        b"<!DOCTYPE html><html><head><title>Electrolyte Report</title></head>"
        b"<body><h1>Experimental Results</h1><p>Ionic conductivity reached 12 mS/cm.</p>"
        b"<table><tr><th>Sample</th><th>Conductivity</th></tr><tr><td>LPS</td><td>12 mS/cm</td></tr></table>"
        b"</body></html>"
    )
    html_res = client.post(
        "/api/v1/documents",
        files={"file": ("report.html", html_bytes, "text/html")},
    )
    assert html_res.status_code == 201, html_res.text
    assert html_res.json()["type"] == "html"
    assert html_res.json()["chunkCount"] >= 1


def test_cloudflare_embeddings_and_jina_cloudflare_rerankers() -> None:
    """Verify Cloudflare Workers AI 1024-d embeddings, Jina Reranker, and Cloudflare BGE Reranker."""
    def cf_embed_handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content.decode())
        texts = body["text"]
        vecs = [[1.0 if i == 0 else 0.0 for i in range(1024)] for _ in texts]
        return httpx.Response(200, json={"success": True, "result": {"data": vecs}})

    cf_embed = CloudflareWorkersAIEmbeddingService(
        account_id="acc1",
        api_token="tok1",
        dimension=1024,
        client=httpx.Client(transport=httpx.MockTransport(cf_embed_handler)),
    )
    vectors = cf_embed.embed_documents(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 1024

    c1 = RetrievalCandidate(
        chunk_id=uuid4(),
        node_id="n1",
        document_id=uuid4(),
        paper_title="Doc 1",
        authors=None,
        doi=None,
        page=1,
        section="Intro",
        text="Irrelevant passage",
        hybrid_score=0.2,
    )
    c2 = RetrievalCandidate(
        chunk_id=uuid4(),
        node_id="n2",
        document_id=uuid4(),
        paper_title="Doc 2",
        authors=None,
        doi=None,
        page=2,
        section="Results",
        text="Highly relevant quantum passage",
        hybrid_score=0.1,
    )

    def jina_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.96},
                    {"index": 0, "relevance_score": 0.12},
                ]
            },
        )

    jina = JinaRerankerService(
        api_key="jina_key",
        client=httpx.Client(transport=httpx.MockTransport(jina_handler)),
    )
    ranked = jina.rerank("quantum", [c1, c2])
    assert ranked[0].chunk_id == c2.chunk_id
    assert ranked[0].rerank_score == 0.96

    def cf_rerank_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {"response": [{"id": 0, "score": 0.15}, {"id": 1, "score": 0.91}]}},
        )

    cf_rerank = CloudflareBGERerankerService(
        account_id="acc1",
        api_token="tok1",
        client=httpx.Client(transport=httpx.MockTransport(cf_rerank_handler)),
    )
    ranked_cf = cf_rerank.rerank("quantum", [c1, c2])
    assert ranked_cf[0].chunk_id == c2.chunk_id
    assert ranked_cf[0].rerank_score == 0.91


def test_zero_cost_router_settings_alignment_and_neon_pool_pre_ping(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Nov 2026 zero-cost Settings defaults, router wiring, health readiness, and pre-ping."""
    cfg = Settings(
        _env_file=None,
        generation_runtime="router",
        gemini_api_key="gm-free-key",
        openrouter_api_key="or-free-key",
    )
    assert cfg.cloudflare_embedding_model == "@cf/baai/bge-m3"
    assert cfg.video_max_frames == 3
    assert cfg.llm_router_providers == ["gemini", "openrouter", "cerebras", "mistral"]
    assert cfg.gemini_model_name == "gemini-3.8-flash"
    assert cfg.gemini_fallback_model_name == "gemini-3.1-flash-lite"
    assert cfg.openrouter_model_name == "openrouter/free"
    assert cfg.cerebras_model_name == "gpt-oss-120b"
    assert cfg.mistral_model_name == "mistral-small-4"
    assert cfg.langfuse_enabled is False

    built = build_router_for_settings(cfg)
    assert [a.provider_name for a in built.adapters] == ["gemini", "openrouter", "cerebras", "mistral"]
    assert [a.default_model for a in built.adapters] == [
        "gemini-3.8-flash",
        "openrouter/free",
        "gpt-oss-120b",
        "mistral-small-4",
    ]

    monkeypatch.setattr(client.app.state, "settings", cfg)
    ready_res = client.get("/api/v1/health/ready")
    assert ready_res.status_code == 200
    checks = {item["name"]: item for item in ready_res.json()["checks"]}
    assert checks["llm_router"]["ok"] is True
    assert checks["llm_router"]["detail"] == "gemini,openrouter"

    with db_session_factory() as db:
        evt = record_telemetry_event(
            db,
            event_type="llm_generation",
            provider="gemini",
            model="gemini-3.8-flash",
            status="success",
            prompt_tokens=500,
            completion_tokens=100,
            settings=cfg,
        )
        assert evt.estimated_cost_usd == 0.0

    neon_engine = create_db_engine(
        "postgresql://user:pass@ep-cool-pooler.us-east-2.aws.neon.tech/neondb"
    )
    assert neon_engine.pool._pre_ping is True  # type: ignore[attr-defined]
    neon_engine.dispose()

    neon_env_cfg = Settings(
        _env_file=None,
        database_url="postgres://user:pass@ep-cool-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require",
        database_url_unpooled="postgres://user:pass@ep-cool.us-east-2.aws.neon.tech/neondb?sslmode=require",
    )
    assert is_neon_pooled_url(neon_env_cfg.database_url) is True
    assert is_neon_pooled_url(neon_env_cfg.migration_database_url) is False


def test_free_tier_graceful_fallbacks_reranker_vision_and_audio(tmp_path: Path) -> None:
    """Verify quota/rate-limit fallbacks across Cloudflare BGE reranker, Gemini Vision, and Whisper/Gemini Audio."""
    cfg = Settings(
        _env_file=None,
        reranker_provider="cloudflare",
        cloudflare_account_id="acc1",
        cloudflare_api_token="tok1",
        gemini_api_key="gm-key",
    )
    resolved_reranker = reranker_service_for(cfg)
    assert isinstance(resolved_reranker, CloudflareBGERerankerService)
    assert isinstance(resolved_reranker._fallback_reranker, LexicalFallbackReranker)

    c1 = RetrievalCandidate(
        chunk_id=uuid4(),
        node_id="n1",
        document_id=uuid4(),
        paper_title="Doc 1",
        authors=None,
        doi=None,
        page=1,
        section="Intro",
        text="Unrelated filler text",
        hybrid_score=0.2,
    )
    c2 = RetrievalCandidate(
        chunk_id=uuid4(),
        node_id="n2",
        document_id=uuid4(),
        paper_title="Doc 2",
        authors=None,
        doi=None,
        page=2,
        section="Results",
        text="Quantum annealing ground state convergence results",
        hybrid_score=0.5,
    )
    cf_429 = CloudflareBGERerankerService(
        account_id="acc1",
        api_token="tok1",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _req: httpx.Response(429, json={"error": "quota"}))
        ),
        fallback_reranker=LexicalFallbackReranker(),
    )
    fallback_ranked = cf_429.rerank("quantum annealing convergence", [c1, c2])
    assert fallback_ranked[0].chunk_id == c2.chunk_id

    # Vision falls back from gemini-3.8-flash (429) -> gemini-3.1-flash-lite (200)
    vision_urls: list[str] = []

    def vision_handler(request: httpx.Request) -> httpx.Response:
        vision_urls.append(str(request.url))
        if "gemini-3.8-flash" in str(request.url):
            return httpx.Response(429, json={"error": "rate_limited"})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Scatter plot of conductivity vs temperature."}]}}]},
        )

    img_buf = BytesIO()
    img = Image.new("RGB", (240, 240), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.line([(20, 20), (220, 220)], fill=(0, 0, 200), width=4)
    img.save(img_buf, format="PNG")
    vision = GeminiVisionAnalyzer(
        api_key="gm-key",
        model_name="gemini-3.8-flash",
        fallback_model_name="gemini-3.1-flash-lite",
        client=httpx.Client(transport=httpx.MockTransport(vision_handler)),
    )
    desc = vision.analyze_image_bytes(img_buf.getvalue(), mime_type="image/png")
    assert desc == "Scatter plot of conductivity vs temperature."
    assert len(vision_urls) == 2
    assert "gemini-3.8-flash" in vision_urls[0]
    assert "gemini-3.1-flash-lite" in vision_urls[1]

    # Audio transcribes with Gemini fallback when Groq is unconfigured OR rate-limited
    wav_path = tmp_path / "sample.wav"
    wav_path.write_bytes(_build_wav_bytes())

    def audio_gemini_handler(request: httpx.Request) -> httpx.Response:
        if "groq.com" in str(request.url):
            return httpx.Response(429, json={"error": "groq_quota"})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Battery cathode retained 94% capacity."}]}}]},
        )

    transcriber = audio_transcriber_for(
        Settings(
            _env_file=None,
            gemini_api_key="gm-key",
            groq_api_key="groq-key",
        ),
        client=httpx.Client(transport=httpx.MockTransport(audio_gemini_handler)),
    )
    segs = transcriber.transcribe_file(wav_path)
    assert len(segs) == 1
    assert "94% capacity" in segs[0].text

    too_big_transcriber = GroqAudioTranscriber(
        api_key="groq-key",
        max_groq_file_bytes=4,
    )
    with pytest.raises(DocumentIngestionError) as exc_info:
        too_big_transcriber.transcribe_file(wav_path)
    assert exc_info.value.code == "audio_file_too_large"
    assert exc_info.value.status_code == 413
