"""Production deployment preparation & quality optimization tests."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4

from docx import Document as WordDocument
from fastapi.testclient import TestClient
import httpx
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import pytest

from app.core.config import Settings
from app.domain.documents import DocumentType
from app.domain.research import ResearchDepth
from app.main import create_app
from app.schemas.retrieval import RetrievalCandidate
from app.services.ingestion import pipeline as ingestion_pipeline
from app.services.ingestion.legacy import LegacyPdfIngestionAdapter
from app.services.ingestion.pipeline import DocumentIngestionError
from app.services.rag.query import _build_followup_evidence, resolve_execution_profile
from app.services.rag.reranking import (
    CloudflareBGERerankerService,
    LexicalFallbackReranker,
    reranker_service_for,
)
from conftest import FRONTEND_HEADERS, FRONTEND_ORIGIN


_TEST_PROD_SECRET = ("test-" * 4) + "prod-key"


def _make_hybrid_pdf(path: Path) -> Path:
    """Page 1 has selectable digital text; Page 2 is an image-only scanned page."""
    text_buf = BytesIO()
    pdf = canvas.Canvas(text_buf)
    pdf.drawString(
        72,
        760,
        "Page 1 digital introduction discussing neural retrieval and attention layers in detail.",
    )
    pdf.showPage()
    pdf.save()

    img_buf = BytesIO()
    Image.new("RGB", (600, 800), (245, 245, 245)).save(img_buf, format="PDF")

    writer = PdfWriter()
    writer.add_page(PdfReader(BytesIO(text_buf.getvalue())).pages[0])
    writer.add_page(PdfReader(BytesIO(img_buf.getvalue())).pages[0])
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _make_scanned_pdf(path: Path, page_count: int = 2) -> Path:
    writer = PdfWriter()
    for index in range(page_count):
        img_buf = BytesIO()
        color = (240 - index * 10, 240, 240)
        Image.new("RGB", (600, 800), color).save(img_buf, format="PDF")
        writer.add_page(PdfReader(BytesIO(img_buf.getvalue())).pages[0])
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _make_docx_file(path: Path) -> Path:
    doc = WordDocument()
    doc.add_heading("Deployment Quality Study", level=0)
    doc.add_heading("Architecture", level=1)
    doc.add_paragraph("Zero-RAM python-docx ingestion extracts structured headings and prose.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Component"
    table.cell(0, 1).text = "RAM"
    table.cell(1, 0).text = "Cloudflare Reranker"
    table.cell(1, 1).text = "0 MB"
    doc.add_heading("Evaluation", level=2)
    doc.add_paragraph("Markdown tables preserve tabular accuracy during retrieval.")
    doc.save(str(path))
    return path


def test_cross_origin_production_cookies_use_samesite_none(tmp_path: Path) -> None:
    from app.db.base import Base

    app = create_app(
        Settings(
            _env_file=None,
            app_environment="production",
            auth_cookie_secure=True,
            api_key_encryption_secret=_TEST_PROD_SECRET,
            database_url=f"sqlite:///{tmp_path / 'prod_cookies.db'}",
            cors_origins=[FRONTEND_ORIGIN],
            rate_limit_enabled=False,
            worker_enabled=False,
            embedding_enabled=False,
            document_ingestion_backend="legacy",
        )
    )
    Base.metadata.create_all(app.state.db_engine)
    try:
        with TestClient(app, headers=FRONTEND_HEADERS) as client:
            reg = client.post(
                "/api/v1/auth/register",
                json={
                    "name": "Cross Origin User",
                    "email": "cross-site@example.com",
                    "password": "very-strong-password-99",
                },
            )
            assert reg.status_code == 201
            login = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "cross-site@example.com",
                    "password": "very-strong-password-99",
                },
            )
            assert login.status_code == 200
            set_cookie = login.headers.get("set-cookie", "").lower()
            assert "samesite=none" in set_cookie
            assert "secure" in set_cookie

            logout = client.post("/api/v1/auth/logout")
            assert logout.status_code == 204
            cleared_cookie = logout.headers.get("set-cookie", "").lower()
            assert "samesite=none" in cleared_cookie
            assert "secure" in cleared_cookie
    finally:
        Base.metadata.drop_all(app.state.db_engine)


def test_legacy_adapter_parses_docx_and_txt_without_docling(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_environment="test",
        document_ingestion_backend="legacy",
        embedding_enabled=False,
        worker_enabled=False,
    )
    adapter = LegacyPdfIngestionAdapter(settings)

    docx_path = _make_docx_file(tmp_path / "report.docx")
    parsed_docx = adapter.parse(
        docx_path,
        document_id=uuid4(),
        ingestion_version="lite-v1",
    )
    assert parsed_docx.parser_name == "python-docx"
    assert parsed_docx.metadata.title == "Deployment Quality Study"
    assert any(node.section == "Architecture" for node in parsed_docx.nodes)
    assert any(
        node.section == "Evaluation"
        and node.section_path == ["Deployment Quality Study", "Architecture", "Evaluation"]
        for node in parsed_docx.nodes
    )
    table_node = next(
        node for node in parsed_docx.nodes if node.metadata.get("content_kind") == "table"
    )
    assert "| Component | RAM |" in table_node.text
    assert "| Cloudflare Reranker | 0 MB |" in table_node.text

    txt_path = tmp_path / "notes.txt"
    txt_path.write_text(
        "1. Overview\nPlain text ingestion preserves headings and paragraphs cleanly.",
        encoding="utf-8",
    )
    parsed_txt = adapter.parse(txt_path, document_id=uuid4(), ingestion_version="lite-v1")
    assert parsed_txt.parser_name == "plain-text"
    assert "Plain text ingestion" in parsed_txt.nodes[0].text

    bad_path = tmp_path / "binary.bin"
    bad_path.write_bytes(b"\x00\x01\x02")
    with pytest.raises(DocumentIngestionError, match="PDF, DOCX, and TXT"):
        adapter.parse(bad_path, document_id=uuid4(), ingestion_version="lite-v1")


def test_legacy_pdf_uses_gemini_flash_ocr_fallback_for_scanned_and_hybrid_pdfs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        parts = body["contents"][0]["parts"]
        inline = next(p["inline_data"] for p in parts if "inline_data" in p)
        calls.append((str(request.url), inline["mime_type"]))

        if "gemini-2.5-flash:" in str(request.url) and len(calls) == 1:
            return httpx.Response(429, request=request, json={"error": "rate limited"})

        if len(calls) <= 2:
            ocr_text = (
                "=== PAGE 1 ===\n"
                "1. Scanned Introduction\n"
                "DOI: 10.1234/ocr.2026.01\n\n"
                "=== PAGE 2 ===\n"
                "| Metric | Score |\n| --- | --- |\n| Recall | 0.96 |"
            )
        else:
            ocr_text = "=== PAGE 1 ===\nScanned appendix page two table data."
        return httpx.Response(
            200,
            request=request,
            json={"candidates": [{"content": {"parts": [{"text": ocr_text}]}}]},
        )

    transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(transport=transport)

    from app.services.ingestion import vision as vision_mod

    orig_factory = vision_mod.vision_analyzer_for
    monkeypatch.setattr(
        vision_mod,
        "vision_analyzer_for",
        lambda settings, **kw: orig_factory(settings, client=mock_client),
    )

    settings = Settings(
        _env_file=None,
        app_environment="test",
        document_ingestion_backend="legacy",
        vision_enabled=True,
        gemini_api_key=("test-" * 2) + "gemini-key",
        gemini_model_name="gemini-2.5-flash",
        gemini_fallback_model_name="gemini-2.5-flash-lite",
        embedding_enabled=False,
        worker_enabled=False,
    )
    adapter = LegacyPdfIngestionAdapter(settings)

    # Full scanned 2-page PDF: hits 429 on primary, automatically retries fallback model.
    scanned_path = _make_scanned_pdf(tmp_path / "scanned.pdf", page_count=2)
    parsed_scan = adapter.parse(
        scanned_path,
        document_id=uuid4(),
        ingestion_version="lite-v1",
    )
    assert parsed_scan.parser_name == "pypdf+gemini-ocr"
    assert parsed_scan.metadata.doi == "10.1234/ocr.2026.01"
    assert any(n.page == 1 and "Scanned Introduction" in n.text for n in parsed_scan.nodes)
    assert any(
        n.page == 2 and "| Metric | Score |" in n.text and n.metadata.get("ocr_provider") == "gemini-vision"
        for n in parsed_scan.nodes
    )
    assert calls[0][1] == "application/pdf"
    assert "gemini-2.5-flash:" in calls[0][0]
    assert "gemini-2.5-flash-lite:" in calls[1][0]

    # Hybrid PDF (page 1 digital, page 2 scanned image): sends ONLY page 2 slice to Gemini!
    hybrid_path = _make_hybrid_pdf(tmp_path / "hybrid.pdf")
    parsed_hybrid = adapter.parse(
        hybrid_path,
        document_id=uuid4(),
        ingestion_version="lite-v1",
    )
    assert len(calls) == 3
    assert any(n.page == 1 and "neural retrieval" in n.text for n in parsed_hybrid.nodes)
    assert any(
        n.page == 2
        and "Scanned appendix page two" in n.text
        and n.metadata.get("ocr_provider") == "gemini-vision"
        for n in parsed_hybrid.nodes
    )

    # Reading stage reports "ocr" for scanned PDFs under legacy+Gemini config.
    fake_pdf_doc = type("Doc", (), {"file_type": DocumentType.PDF})()
    assert ingestion_pipeline._reading_stage(fake_pdf_doc, scanned_path, settings) == "ocr"

    # Without GEMINI_API_KEY, a scanned PDF still returns a clear error instead of silent empty indexing.
    no_key_adapter = LegacyPdfIngestionAdapter(
        settings.model_copy(update={"gemini_api_key": None})
    )
    with pytest.raises(DocumentIngestionError, match="no extractable text"):
        no_key_adapter.parse(scanned_path, document_id=uuid4(), ingestion_version="lite-v1")


def test_cloudflare_reranker_active_on_max_quality_and_falls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    max_quality = Settings(
        _env_file=None,
        app_environment="test",
        reranker_provider="cloudflare",
        cloudflare_account_id="acct-123",
        cloudflare_api_token="cf-token",
        adaptive_fast_path_enabled=False,
    )
    for depth in (ResearchDepth.QUICK, ResearchDepth.STANDARD, ResearchDepth.DEEP):
        profile = resolve_execution_profile("What is LoRA?", depth, max_quality)
        assert profile.settings.reranker_provider == "cloudflare"

    # Standard complex & deep queries ALSO keep cloudflare when adaptive fast path is enabled.
    adaptive = max_quality.model_copy(update={"adaptive_fast_path_enabled": True})
    assert (
        resolve_execution_profile("Compare LoRA and QLoRA in detail", ResearchDepth.STANDARD, adaptive)
        .settings.reranker_provider
        == "cloudflare"
    )
    assert (
        resolve_execution_profile("What is LoRA?", ResearchDepth.DEEP, adaptive)
        .settings.reranker_provider
        == "cloudflare"
    )

    # Verify CloudflareBGERerankerService scores candidates accurately, and silently falls back on quota 429.
    candidates = [
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            paper_title="A",
            authors=None,
            doi=None,
            page=1,
            section="Intro",
            text="Unrelated compiler pass details.",
            vector_score=0.6,
            hybrid_score=0.02,
        ),
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            paper_title="B",
            authors=None,
            doi=None,
            page=2,
            section="Results",
            text="Cloudflare BGE reranker dramatically improves precision on standard queries.",
            vector_score=0.75,
            hybrid_score=0.03,
        ),
    ]

    ok_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                request=req,
                json={"result": {"response": [{"id": 0, "score": 0.12}, {"id": 1, "score": 0.94}]}},
            )
        )
    )
    cf_svc = CloudflareBGERerankerService(
        account_id="acct-123",
        api_token="cf-token",
        client=ok_client,
        fallback_reranker=LexicalFallbackReranker(),
    )
    ranked_ok = cf_svc.rerank("cloudflare reranker precision", candidates)
    assert ranked_ok[0].paper_title == "B"
    assert ranked_ok[0].rerank_score == pytest.approx(0.94)

    quota_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, request=req, json={"errors": [{"message": "daily quota"}]})
        )
    )
    cf_quota_svc = CloudflareBGERerankerService(
        account_id="acct-123",
        api_token="cf-token",
        client=quota_client,
        fallback_reranker=LexicalFallbackReranker(),
    )
    ranked_fallback = cf_quota_svc.rerank("cloudflare reranker precision", candidates)
    assert ranked_fallback[0].paper_title == "B"
    assert isinstance(reranker_service_for(max_quality), CloudflareBGERerankerService)

    # Verify _build_followup_evidence honors ADAPTIVE_FAST_PATH_ENABLED=false by keeping cloudflare reranker.
    from app.services.rag import query as query_mod

    seen_providers: list[str] = []
    fake_record = type(
        "Rec",
        (),
        {
            "project_id": None,
            "question": "Initial research question",
            "documents_scoped": False,
            "document_ids": [],
        },
    )()
    monkeypatch.setattr(query_mod.retrieval, "retrieve", lambda *a, **kw: candidates)

    class _RecordingReranker:
        def __init__(self, provider: str) -> None:
            seen_providers.append(provider)

        def rerank(self, query: str, items: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
            return items

    monkeypatch.setattr(
        query_mod,
        "reranker_service_for",
        lambda s: _RecordingReranker(s.reranker_provider),
    )
    _build_followup_evidence(
        None,  # type: ignore[arg-type]
        record=fake_record,  # type: ignore[arg-type]
        user_id=uuid4(),
        question="Why did precision improve?",
        existing_sources=[],
        settings=max_quality,
        reranker=None,
    )
    _build_followup_evidence(
        None,  # type: ignore[arg-type]
        record=fake_record,  # type: ignore[arg-type]
        user_id=uuid4(),
        question="Why did precision improve?",
        existing_sources=[],
        settings=adaptive,
        reranker=None,
    )
    assert seen_providers == ["cloudflare", "lexical"]


def test_requirements_prod_lite_excludes_heavy_ml_and_includes_runtime_deps() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    req_text = (repo_root / "backend" / "requirements-prod-lite.txt").read_text(encoding="utf-8")
    packages = {
        line.strip().split(">=")[0].split("==")[0].split("[")[0].lower()
        for line in req_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for heavy in ("torch", "docling", "llama-index", "sentence-transformers", "transformers"):
        assert all(heavy not in pkg for pkg in packages), f"Unexpected heavy package: {heavy}"
    for required in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg", "pgvector", "numpy", "python-docx", "pypdf", "pillow", "httpx"):
        assert required in packages
