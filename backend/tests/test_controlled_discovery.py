"""Unit, integration, and end-to-end tests for Controlled Discovery."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType
from app.models.document import Document, DocumentChunk
from app.models.report import Source
from app.models.research import Research
from app.services.discovery import providers as discovery_providers
from app.services.discovery import service as discovery_service
from app.schemas.discovery import DiscoverySearchResponse
from app.services.documents.storage import LocalDocumentStorage
from app.services.ingestion import pipeline as ingestion_service
from app.services.rag import query as rag_service
from conftest import FRONTEND_HEADERS
from test_architecture_upgrade import DeterministicEmbeddingService, KeywordAwareReranker
from test_documents_api import make_pdf


_ARXIV_ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T00:00:00Z</published>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose a new simple network architecture, the Transformer.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/1706.03762v7"/>
    <link title="pdf" rel="related" type="application/pdf" href="http://arxiv.org/pdf/1706.03762v7"/>
  </entry>
</feed>
"""


def _build_mock_transport(
    *,
    pdf_bytes: bytes,
    fail_wikipedia: bool = False,
    paywall_pdf_urls: set[str] | None = None,
    requested_urls: list[str] | None = None,
) -> httpx.MockTransport:
    paywalled = paywall_pdf_urls or set()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if requested_urls is not None:
            requested_urls.append(url)

        if url in paywalled:
            return httpx.Response(403, text="Subscription required")

        if url.startswith("https://api.openalex.org/works"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W2626778328",
                            "doi": "https://doi.org/10.5555/3295222.3295349",
                            "title": "Attention Is All You Need",
                            "publication_year": 2017,
                            "cited_by_count": 98000,
                            "type": "article",
                            "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/1706.03762.pdf"},
                            "best_oa_location": {
                                "landing_page_url": "https://papers.nips.cc/paper/7181-attention-is-all-you-need",
                                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                            },
                            "primary_location": {
                                "landing_page_url": "https://papers.nips.cc/paper/7181-attention-is-all-you-need",
                                "source": {"display_name": "NeurIPS"},
                            },
                            "authorships": [
                                {"author": {"display_name": "Ashish Vaswani"}},
                                {"author": {"display_name": "Noam Shazeer"}},
                            ],
                            "abstract_inverted_index": {
                                "Transformer": [0],
                                "self-attention": [1],
                                "replaces": [2],
                                "recurrence": [3],
                                "completely.": [4],
                            },
                        }
                    ]
                },
            )

        if url.startswith("https://api.crossref.org/works"):
            return httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.5555/3295222.3295349",
                                "title": ["Attention Is All You Need"],
                                "author": [{"given": "Ashish", "family": "Vaswani"}],
                                "published-print": {"date-parts": [[2017]]},
                                "container-title": ["NeurIPS"],
                                "abstract": "<jats:p>A longer Crossref verified abstract about self-attention sequence transduction models.</jats:p>",
                                "is-referenced-by-count": 42000,
                                "URL": "https://doi.org/10.5555/3295222.3295349",
                                "type": "proceedings-article",
                            },
                            {
                                "DOI": "10.1000/paywalled.study",
                                "title": ["Paywalled Clinical Study"],
                                "author": [{"given": "Grace", "family": "Hopper"}],
                                "published-online": {"date-parts": [[2023]]},
                                "container-title": ["Journal of Verified Science"],
                                "abstract": "<jats:p>Randomized clinical findings demonstrating measurable reliability gains from curated evidence.</jats:p>",
                                "is-referenced-by-count": 125,
                                "URL": "https://publisher.example.org/study",
                                "type": "journal-article",
                                "link": [
                                    {
                                        "URL": "https://publisher.example.org/paywalled.pdf",
                                        "content-type": "application/pdf",
                                    }
                                ],
                            },
                        ]
                    }
                },
            )

        if url.startswith("https://export.arxiv.org/api/query"):
            return httpx.Response(200, text=_ARXIV_ATOM_SAMPLE)

        if url.startswith("https://en.wikipedia.org/w/api.php"):
            if fail_wikipedia:
                return httpx.Response(503, text="Wikipedia maintenance")
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "12345": {
                                "index": 1,
                                "title": "Transformer (deep learning architecture)",
                                "extract": "A transformer is a deep learning architecture developed by researchers at Google and based on the multi-head attention mechanism.",
                                "fullurl": "https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)",
                            }
                        }
                    }
                },
            )

        if url.startswith("https://arxiv.org/pdf/"):
            return httpx.Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})

        if url.startswith("https://en.wikipedia.org/wiki/") or url.startswith("https://r.jina.ai/"):
            return httpx.Response(
                200,
                text="<html><head><title>Transformer</title></head><body><main><h1>Overview</h1><p>A transformer uses self-attention across all sequence positions.</p></main></body></html>",
                headers={"content-type": "text/html"},
            )

        return httpx.Response(404, text="Not found")

    return httpx.MockTransport(handler)


class _CitedGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, question: str, evidence, **_kwargs) -> str:
        self.calls += 1
        assert len(evidence) >= 1
        return f"Self-attention replaces recurrence in Transformer models [{evidence[0].source_id}]."


def test_provider_normalization_deduplication_and_partial_outage() -> None:
    assert discovery_providers.normalize_doi("https://doi.org/10.1000/XYZ.") == "10.1000/xyz"
    assert discovery_providers.strip_jats_xml("<jats:p>Hello &amp; <b>world</b>.</jats:p>") == "Hello & world ."
    assert (
        discovery_providers.reconstruct_openalex_abstract({"Self": [0], "attention": [1], "works": [2]})
        == "Self attention works"
    )
    assert discovery_providers.is_trusted_domain("en.wikipedia.org") is True
    assert discovery_providers.is_trusted_domain("stanford.edu") is True
    assert discovery_providers.is_trusted_domain("random-seo-blog.biz") is False

    transport = _build_mock_transport(pdf_bytes=make_pdf("Transformer self-attention"), fail_wikipedia=True)
    with httpx.Client(transport=transport) as mock_client:
        outcome = discovery_providers.search_curated_sources(
            "transformer attention",
            scope="all",
            limit=8,
            client=mock_client,
        )

    assert len(outcome.provider_errors) == 1
    assert "wikipedia" in outcome.provider_errors[0].lower()

    titles = [item.title for item in outcome.items]
    # OpenAlex + Crossref (same DOI) + arXiv (normalized identical title) deduplicate into one canonical entry!
    assert titles.count("Attention Is All You Need") == 1
    attention = next(item for item in outcome.items if item.title == "Attention Is All You Need")
    assert attention.provider == "openalex"
    assert attention.trust_tier == "peer-reviewed"
    assert attention.open_access_pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
    assert attention.content_level == ContentLevel.FULL_TEXT
    assert attention.abstract is not None and "sequence transduction models" in attention.abstract

    paywalled = next(item for item in outcome.items if item.title == "Paywalled Clinical Study")
    assert paywalled.doi == "10.1000/paywalled.study"
    assert paywalled.publisher == "Journal of Verified Science"


def test_import_enforces_ssrf_oa_pdf_full_text_and_abstract_fallback(
    client: TestClient,
    db_session: Session,
    upload_dir: Path,
    test_settings: Settings,
    monkeypatch,
) -> None:
    test_settings.embedding_enabled = True
    test_settings.allow_sqlite_retrieval_fallback = True
    embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr(ingestion_service, "embedding_service_for", lambda _s: embeddings)

    me = client.get("/api/v1/auth/me").json()
    user_id = UUID(me["id"])

    requested_urls: list[str] = []
    pdf_bytes = make_pdf(
        "1 INTRODUCTION\nTransformers compute scaled dot-product self-attention across sequence tokens.",
        title="Attention Is All You Need",
    )
    transport = _build_mock_transport(
        pdf_bytes=pdf_bytes,
        paywall_pdf_urls={"https://publisher.example.org/paywalled.pdf"},
        requested_urls=requested_urls,
    )

    from app.schemas.discovery import DiscoveredSourceCandidate

    ssrf_candidate = DiscoveredSourceCandidate(
        candidate_id="openalex-ssrf",
        provider="openalex",
        trust_tier="peer-reviewed",
        source_type=SourceType.OPENALEX,
        content_level=ContentLevel.FULL_TEXT,
        title="Internal Secret",
        url="https://example.org/paper",
        open_access_pdf_url="http://127.0.0.1/secret.pdf",
        abstract="Fallback text should never execute when PDF URL is unsafe SSRF.",
    )
    oa_candidate = DiscoveredSourceCandidate(
        candidate_id="openalex-oa",
        provider="openalex",
        trust_tier="peer-reviewed",
        source_type=SourceType.OPENALEX,
        content_level=ContentLevel.FULL_TEXT,
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        publication_year=2017,
        publisher="NeurIPS",
        doi="10.5555/3295222.3295349",
        openalex_id="W2626778328",
        url="https://papers.nips.cc/paper/7181-attention-is-all-you-need",
        open_access_pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
        abstract="Fallback abstract.",
        is_open_access=True,
    )
    paywalled_candidate = DiscoveredSourceCandidate(
        candidate_id="crossref-paywall",
        provider="crossref",
        trust_tier="peer-reviewed",
        source_type=SourceType.CROSSREF,
        content_level=ContentLevel.FULL_TEXT,
        title="Paywalled Clinical Study",
        authors=["Grace Hopper"],
        publication_year=2023,
        publisher="Journal of Verified Science",
        doi="10.1000/paywalled.study",
        crossref_id="10.1000/paywalled.study",
        url="https://publisher.example.org/study",
        open_access_pdf_url="https://publisher.example.org/paywalled.pdf",
        abstract="Randomized clinical findings demonstrating measurable reliability gains from curated evidence.",
        is_open_access=False,
    )

    storage = LocalDocumentStorage(upload_dir, test_settings.document_max_upload_bytes)
    with httpx.Client(transport=transport) as mock_client:
        result = discovery_service.import_discovered_sources(
            db_session,
            [ssrf_candidate, oa_candidate, paywalled_candidate],
            storage=storage,
            settings=test_settings,
            user_id=user_id,
            fetch_full_text=True,
            embeddings=embeddings,
            client=mock_client,
        )

    assert not any("127.0.0.1" in u for u in requested_urls)
    assert len(result.failed) == 1
    assert "Private" in result.failed[0].reason or "loopback" in result.failed[0].reason

    assert result.imported_count == 2
    assert len(result.documents) == 2

    oa_doc, abstract_doc = result.documents
    assert oa_doc.status == DocumentStatus.INDEXED
    assert oa_doc.file_type == DocumentType.PDF
    assert oa_doc.content_level == ContentLevel.FULL_TEXT
    assert (oa_doc.canonical_metadata or {}).get("publisher") == "NeurIPS"
    assert oa_doc.publication_year == 2017

    assert abstract_doc.status == DocumentStatus.INDEXED
    assert abstract_doc.file_type == DocumentType.WEB
    assert abstract_doc.content_level == ContentLevel.ABSTRACT
    chunks = list(db_session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == abstract_doc.id)))
    assert len(chunks) >= 1
    assert "Randomized clinical findings" in chunks[0].text


def test_discovery_api_library_annotation_reuse_and_project_isolation(
    client: TestClient,
    test_app,
    monkeypatch,
) -> None:
    pdf_bytes = make_pdf("Self-attention replaces recurrent connections cleanly.")
    transport = _build_mock_transport(pdf_bytes=pdf_bytes)
    real_client = httpx.Client

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(transport=transport),
    )

    status_res = client.get("/api/v1/discovery/status")
    assert status_res.status_code == 200
    assert status_res.json()["enabled"] is True

    search_res = client.post(
        "/api/v1/discovery/search",
        json={"query": "Attention Is All You Need", "scope": "all", "limit": 8},
    )
    assert search_res.status_code == 200, search_res.text
    items = search_res.json()["items"]
    assert len(items) >= 2
    assert all(item["alreadyInLibrary"] is False for item in items)

    chosen = next(item for item in items if item["title"] == "Attention Is All You Need")
    first_import = client.post(
        "/api/v1/discovery/import",
        json={"items": [chosen], "fetchFullText": True},
    )
    assert first_import.status_code == 201, first_import.text
    import_body = first_import.json()
    assert import_body["importedCount"] == 1
    assert import_body["reusedCount"] == 0
    doc_id = import_body["documents"][0]["id"]

    # Searching again must mark the same source as alreadyInLibrary with its documentId.
    search_again = client.post(
        "/api/v1/discovery/search",
        json={"query": "Attention Is All You Need", "scope": "all"},
    )
    assert search_again.status_code == 200
    matched = next(item for item in search_again.json()["items"] if item["title"] == "Attention Is All You Need")
    assert matched["alreadyInLibrary"] is True
    assert matched["existingDocumentId"] == doc_id

    # Importing again idempotently reuses the existing indexed document.
    second_import = client.post(
        "/api/v1/discovery/import",
        json={"items": [chosen], "fetchFullText": True},
    )
    assert second_import.status_code == 201
    assert second_import.json()["importedCount"] == 0
    assert second_import.json()["reusedCount"] == 1
    assert second_import.json()["documents"][0]["id"] == doc_id

    # Foreign project isolation: user B's project returns 404 for user A.
    with TestClient(test_app, headers=FRONTEND_HEADERS) as other_client:
        reg = other_client.post(
            "/api/v1/auth/register",
            json={"name": "Other", "email": "other-disc@example.com", "password": "other-password-123"},
        )
        assert reg.status_code == 201
        login = other_client.post(
            "/api/v1/auth/login",
            json={"email": "other-disc@example.com", "password": "other-password-123"},
        )
        assert login.status_code == 200
        foreign_proj = other_client.post("/api/v1/projects", json={"name": "Secret Project"}).json()

    forbidden_search = client.post(
        "/api/v1/discovery/search",
        json={"query": "Attention", "projectId": foreign_proj["id"]},
    )
    assert forbidden_search.status_code == 404

    forbidden_import = client.post(
        "/api/v1/discovery/import",
        json={"items": [chosen], "projectId": foreign_proj["id"]},
    )
    assert forbidden_import.status_code == 404


def test_auto_discover_opt_in_end_to_end_and_default_guard(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    # Default mode without autoDiscover still enforces explicit local document requirement.
    blocked = client.post(
        "/api/v1/research/query",
        json={"query": "What is self-attention?", "documentIds": [], "autoDiscover": False},
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "research_documents_required"

    settings = client.app.state.settings
    settings.embedding_enabled = True
    settings.allow_sqlite_retrieval_fallback = True
    embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda _s: KeywordAwareReranker())
    generator = _CitedGenerator()
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)

    pdf_bytes = make_pdf(
        "1 INTRODUCTION\nSelf-attention replaces recurrence in Transformer models and improves parallelization.",
        title="Attention Is All You Need",
    )
    transport = _build_mock_transport(pdf_bytes=pdf_bytes)
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(transport=transport),
    )

    response = client.post(
        "/api/v1/research/query",
        json={
            "query": "How does self-attention work in Transformer models?",
            "documentIds": [],
            "autoDiscover": True,
            "discoveryScope": "scholarly",
            "researchDepth": "quick",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert generator.calls == 1
    assert body["insufficientEvidence"] is False
    assert len(body["citations"]) >= 1
    first_citation = body["citations"][0]
    assert first_citation["url"] is not None
    assert first_citation["publisher"] is not None
    assert first_citation["year"] is not None

    research_id = UUID(body["researchId"])
    record = db_session.get(Research, research_id)
    assert record is not None
    assert record.documents_scoped is True
    assert len(record.document_ids) >= 1

    sources = list(
        db_session.scalars(select(Source).where(Source.research_id == research_id).order_by(Source.number))
    )
    assert len(sources) >= 1
    assert sources[0].source_type.value == "peer-reviewed"
    assert sources[0].publisher == "NeurIPS"
    assert sources[0].year == 2017
    assert sources[0].doi == "10.5555/3295222.3295349"
    assert sources[0].url is not None


def test_auto_discover_job_returns_at_once_and_discovers_in_the_background(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = client.app.state.settings
    settings.embedding_enabled = True
    settings.allow_sqlite_retrieval_fallback = True
    embeddings = DeterministicEmbeddingService()
    monkeypatch.setattr("app.services.ingestion.pipeline.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr("app.services.rag.retrieval.embedding_service_for", lambda _s: embeddings)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda _s: KeywordAwareReranker())
    generator = _CitedGenerator()
    monkeypatch.setattr(rag_service, "generation_service_for", lambda _s: generator)

    pdf_bytes = make_pdf(
        "1 INTRODUCTION\nSelf-attention replaces recurrence in Transformer models and improves parallelization.",
        title="Attention Is All You Need",
    )
    requested_urls: list[str] = []
    transport = _build_mock_transport(pdf_bytes=pdf_bytes, requested_urls=requested_urls)
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(transport=transport),
    )

    queued = client.post(
        "/api/v1/research/jobs",
        json={
            "query": "How does self-attention work in Transformer models?",
            "autoDiscover": True,
            "discoveryScope": "scholarly",
        },
    )
    assert queued.status_code == 202, queued.text
    research_id = queued.json()["id"]
    # Nothing is searched or downloaded while the request is open.
    assert requested_urls == []
    assert generator.calls == 0
    record = db_session.get(Research, UUID(research_id))
    assert record is not None
    assert record.discovery_scope == "scholarly"
    assert record.documents_scoped is False

    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "researching"
    assert progress["autoDiscover"] is True
    titles = [step["title"] for step in progress["steps"]]
    assert "Finding sources" in titles

    assert client.app.state.job_worker.run_until_empty() == 1
    assert requested_urls
    assert generator.calls == 1
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "completed"

    db_session.expire_all()
    record = db_session.get(Research, UUID(research_id))
    assert record.documents_scoped is True
    assert len(record.document_ids) >= 1
    report = client.get(f"/api/v1/research/{research_id}/report").json()
    assert report["report"]["sourceCount"] >= 1


def test_auto_discover_job_that_finds_nothing_fails_on_the_progress_page(
    client: TestClient,
    monkeypatch,
) -> None:
    def no_results(_session, *, query, scope, **_kwargs):
        return DiscoverySearchResponse(query=query, scope=scope, items=[])

    monkeypatch.setattr(discovery_service, "search_and_annotate", no_results)

    queued = client.post(
        "/api/v1/research/jobs",
        json={"query": "Something nobody has written about?", "autoDiscover": True},
    )
    assert queued.status_code == 202, queued.text
    research_id = queued.json()["id"]

    client.app.state.job_worker.run_until_empty()
    progress = client.get(f"/api/v1/research/{research_id}/status").json()
    assert progress["status"] == "failed"
    assert progress["failureReason"] == "no_discoverable_sources"
    failed_steps = [step for step in progress["steps"] if step["status"] == "failed"]
    assert [step["id"] for step in failed_steps] == ["searching_sources"]


def test_auto_discover_job_is_refused_up_front_when_discovery_is_off(client: TestClient) -> None:
    client.app.state.settings.discovery_enabled = False
    response = client.post(
        "/api/v1/research/jobs",
        json={"query": "How does self-attention work?", "autoDiscover": True},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "discovery_disabled"


def test_query_distillation_relevance_scoring_and_wikipedia_sections() -> None:
    assert (
        discovery_providers.distill_search_query(
            "tell me about lithium carbonate usage in medical terms, how it works?"
        )
        == "lithium carbonate medical"
    )
    assert (
        discovery_providers.distill_search_query("attention is all you need")
        == "attention is all you need"
    )

    from app.schemas.discovery import DiscoveredSourceCandidate

    off_topic = DiscoveredSourceCandidate(
        candidate_id="oa-offtopic",
        provider="openalex",
        trust_tier="peer-reviewed",
        source_type=SourceType.OPENALEX,
        content_level=ContentLevel.FULL_TEXT,
        title="Self-Tracking for Health and the Quantified Self",
        abstract="Digital health tracking applications in general care.",
        url="https://example.org/offtopic",
        citation_count=50000,
    )
    wiki_medical = DiscoveredSourceCandidate(
        candidate_id="wiki-lithium",
        provider="wikipedia",
        trust_tier="institutional",
        source_type=SourceType.WEB_PAGE,
        content_level=ContentLevel.WEB_PAGE,
        title="Lithium carbonate",
        abstract="Lithium carbonate is used medically as a mood stabilizer in bipolar disorder.",
        url="https://en.wikipedia.org/wiki/Lithium_carbonate",
    )
    core_terms = {"lithium", "carbonate", "medical"}
    subject_terms = {"lithium", "carbonate"}
    assert discovery_providers._score_candidate(
        wiki_medical, core_terms, subject_terms, "lithium carbonate"
    ) > discovery_providers._score_candidate(
        off_topic, core_terms, subject_terms, "lithium carbonate"
    )

    parsed_wiki = discovery_service._parse_wikipedia_extract(
        wiki_medical,
        "Lead intro paragraph explaining mood stabilization.\n\n"
        "== Medical uses ==\nLithium carbonate treats acute mania and bipolar disorder.\n\n"
        "== References ==\n1. Citation should be skipped.",
        document_id=UUID("11111111-1111-1111-1111-111111111111"),
        ingestion_version="v1",
        chunk_size=1000,
        overlap=100,
    )
    assert parsed_wiki is not None
    headings = [node.section for node in parsed_wiki.nodes]
    assert "Medical uses" in headings
    assert "References" not in headings


def test_reputable_news_rss_multi_part_distillation_and_contradiction_prompt(
    tmp_path: Path,
) -> None:
    from app.schemas.rag import EvidenceItem
    from app.services.documents.storage import R2DocumentStorage
    from app.services.rag import query as query_mod
    from app.services.rag.generation import build_grounding_prompt

    # Multi-part news/historical question distills cleanly without conversational/temporal noise.
    assert (
        discovery_providers.distill_search_query(
            "Why Israel and Iran war happening? What is the historical reason behind it? What is the latest news about it?"
        )
        == "israel iran war"
    )

    bing_rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0" xmlns:News="http://schemas.microsoft.com/news/2008">
      <channel>
        <item>
          <title>Israel and Iran trade strikes amid regional escalation</title>
          <link>https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fwww.reuters.com%2Fworld%2Fmiddle-east%2Fisrael-iran-strikes&amp;tid=1</link>
          <description>Officials gave conflicting casualty estimates following overnight strikes.</description>
          <pubDate>Tue, 24 Nov 2026 01:00:00 GMT</pubDate>
          <News:Source>Reuters</News:Source>
        </item>
        <item>
          <title>Random Unverified Blog Post About Rumors</title>
          <link>https://random-gossip-blog.example.com/post</link>
          <description>Unverified rumor post that should be filtered out.</description>
          <pubDate>Tue, 24 Nov 2026 01:00:00 GMT</pubDate>
          <News:Source>Random Gossip Blog</News:Source>
        </item>
      </channel>
    </rss>"""

    google_rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Diplomatic rift deepens over Iran-Israel conflict - Al Jazeera</title>
          <link>https://news.google.com/rss/articles/CBMiTestArticle</link>
          <pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate>
          <description>&lt;a href="https://news.google.com/rss/articles/CBMiTestArticle"&gt;Diplomatic rift deepens&lt;/a&gt; Al Jazeera</description>
          <source url="https://www.aljazeera.com">Al Jazeera</source>
        </item>
      </channel>
    </rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://www.bing.com/news/search"):
            return httpx.Response(200, text=bing_rss)
        if url.startswith("https://news.google.com/rss/search"):
            return httpx.Response(200, text=google_rss)
        return httpx.Response(404, text="Not found")

    with httpx.Client(transport=httpx.MockTransport(handler)) as mock_client:
        news_items = discovery_providers.search_reputable_news(
            "israel iran war",
            limit=4,
            client=mock_client,
        )

    assert [item.publisher for item in news_items] == ["Reuters", "Al Jazeera"]
    assert news_items[0].url == "https://www.reuters.com/world/middle-east/israel-iran-strikes"
    assert "conflicting casualty estimates" in (news_items[0].abstract or "")
    assert news_items[0].publication_year == 2026
    assert news_items[1].title == "Diplomatic rift deepens over Iran-Israel conflict"

    # Source selection interleaves scholarly, Wikipedia, and reputable news sources under scope="all".
    wiki_cand = discovery_providers.DiscoveredSourceCandidate(
        candidate_id="wiki-1",
        provider="wikipedia",
        trust_tier="institutional",
        source_type=SourceType.WEB_PAGE,
        content_level=ContentLevel.WEB_PAGE,
        title="Iran-Israel proxy conflict",
        publisher="Wikipedia",
        abstract="Historical background on the Iran-Israel conflict.",
        url="https://en.wikipedia.org/wiki/Iran%E2%80%93Israel_proxy_conflict",
    )
    scholarly_cands = [
        discovery_providers.DiscoveredSourceCandidate(
            candidate_id=f"oa-{i}",
            provider="openalex",
            trust_tier="peer-reviewed",
            source_type=SourceType.OPENALEX,
            content_level=ContentLevel.ABSTRACT,
            title=f"Academic Paper {i}",
            publisher="Journal",
            abstract="Peer reviewed historical analysis.",
            url=f"https://doi.org/10.1000/test.{i}",
        )
        for i in range(3)
    ]
    diversified = query_mod._select_diverse_discovery_candidates(
        [*scholarly_cands, wiki_cand, *news_items],
        scope="all",
    )
    first_three_publishers = [item.publisher for item in diversified[:3]]
    assert "Reuters" in first_three_publishers
    assert "Wikipedia" in first_three_publishers
    assert "Journal" in first_three_publishers

    # R2 endpoint normalization strips trailing /{bucket} and whitespace/quotes, and discovery keeps local copy on R2 error.
    r2 = R2DocumentStorage(
        tmp_path / "uploads",
        1024 * 1024,
        bucket_name="research-documents",
        access_key_id="access-key",
        secret_access_key="secret-key",
        endpoint_url=' "https://acct123.r2.cloudflarestorage.com/research-documents/" ',
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(403, text="Forbidden"))
        ),
    )
    assert r2.endpoint_url == "https://acct123.r2.cloudflarestorage.com"
    stored_name, backend_name, _checksum, size = discovery_service._save_stored_bytes(
        r2, b"discovery evidence", extension=".web", content_type="text/plain"
    )
    assert backend_name == "local"
    assert size == len(b"discovery evidence")
    assert (r2.root / stored_name).is_file()

    # Grounding prompt exposes publisher + year and instructs surfacing contradictions.
    prompt = build_grounding_prompt(
        "Why Israel and Iran war happening? What is the latest news?",
        [
            EvidenceItem(
                source_id="S1",
                node_id="n1",
                document_id=UUID("11111111-1111-1111-1111-111111111111"),
                source_type=SourceType.WEB_PAGE,
                content_level=ContentLevel.WEB_PAGE,
                chunk_id=UUID("22222222-2222-2222-2222-222222222222"),
                paper_title="Reuters Report",
                authors=None,
                doi=None,
                page=1,
                section="Report",
                publisher="Reuters",
                year=2026,
                text="Reuters reports casualty figure A.",
                rerank_score=0.9,
            ),
        ],
    )
    assert 'publisher="Reuters"' in prompt
    assert 'year="2026"' in prompt
    assert "contradiction" in prompt.lower()


def test_arxiv_requires_every_key_word_then_falls_back_to_loose_query() -> None:
    seen: list[str] = []
    empty_feed = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["search_query"]
        seen.append(query)
        if " AND " in query:
            return httpx.Response(200, text=empty_feed)
        return httpx.Response(200, text=_ARXIV_ATOM_SAMPLE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items = discovery_providers.search_arxiv("retrieval augmented generation reranking", client=client)

    assert seen == [
        "all:retrieval AND all:augmented AND all:generation AND all:reranking",
        "all:retrieval AND all:augmented AND all:generation",
        "all:retrieval augmented generation reranking",
    ]
    assert len(items) == 1


def test_arxiv_single_word_query_skips_the_strict_search() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["search_query"])
        return httpx.Response(200, text=_ARXIV_ATOM_SAMPLE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        discovery_providers.search_arxiv("transformers", client=client)

    assert seen == ["all:transformers"]
