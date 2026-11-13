"""Tests for Phase 8: Observability, Langfuse-compatible telemetry, and Ragas-style RAG evaluation."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.schemas.rag import EvidenceItem
from app.services.observability.evaluation import (
    EvaluationBenchmarkCase,
    run_evaluation_suite,
)
from app.services.observability.telemetry import (
    record_telemetry_event,
    sanitize_metadata,
    summarize_telemetry,
)


def test_telemetry_secret_sanitization_and_summary(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    """Ensure secrets/prompts are stripped from telemetry metadata and summary aggregates accurately."""
    dirty_meta = {
        "api_key": "sk-secret-value",
        "prompt": "private user prompt",
        "document_text": "confidential text",
        "fallback_attempts": 1,
        "provider_region": "us-east",
    }
    cleaned = sanitize_metadata(dirty_meta)
    assert "api_key" not in cleaned
    assert "prompt" not in cleaned
    assert "document_text" not in cleaned
    assert cleaned["fallback_attempts"] == 1
    assert cleaned["provider_region"] == "us-east"

    me = client.get("/api/v1/auth/me").json()
    from uuid import UUID

    user_id = UUID(me["id"])
    with db_session_factory() as db:
        record_telemetry_event(
            db,
            event_type="llm_generation",
            provider="gemini",
            model="gemini-2.5-flash",
            status="success",
            latency_ms=120.5,
            prompt_tokens=1000,
            completion_tokens=200,
            user_id=user_id,
            metadata=dirty_meta,
        )
        record_telemetry_event(
            db,
            event_type="llm_generation",
            provider="cerebras",
            model="llama-3.3-70b",
            status="error",
            error_code="RateLimitError",
            latency_ms=45.0,
            user_id=user_id,
        )
        summary = summarize_telemetry(db, user_id=user_id)
        assert summary["total_events"] == 2
        assert summary["error_count"] == 1
        assert summary["total_tokens"] == 1200
        assert summary["by_provider"]["gemini"]["requests"] == 1

    res = client.get("/api/v1/telemetry/summary")
    assert res.status_code == 200
    assert res.json()["total_events"] == 2


def test_ragas_style_evaluation_suite() -> None:
    """Evaluate retrieval context precision, recall, answer faithfulness, relevance, and citation accuracy."""
    doc_id = uuid4()
    chunk_1 = uuid4()
    chunk_2 = uuid4()

    evidence = [
        EvidenceItem(
            source_id="S1",
            node_id="node-1",
            document_id=doc_id,
            chunk_id=chunk_1,
            paper_title="Neon Serverless PostgreSQL Whitepaper",
            authors=["Nikita Shamgunov"],
            doi="10.1000/neon.2025",
            page=3,
            section="Architecture",
            text=(
                "Neon separates compute and storage using multi-tenant page servers "
                "and supports pgvector HNSW indexes for 1024-dimensional embeddings."
            ),
            rerank_score=0.94,
        ),
        EvidenceItem(
            source_id="S2",
            node_id="node-2",
            document_id=doc_id,
            chunk_id=chunk_2,
            paper_title="Neon Serverless PostgreSQL Whitepaper",
            authors=["Nikita Shamgunov"],
            doi="10.1000/neon.2025",
            page=5,
            section="Connection Pooling",
            text=(
                "PgBouncer connection pooling handles up to 10,000 concurrent connections "
                "with transaction pooling mode."
            ),
            rerank_score=0.88,
        ),
    ]

    case = EvaluationBenchmarkCase(
        case_id="neon-pgvector-architecture",
        question="How does Neon architecture support pgvector embeddings and connection pooling?",
        expected_facts=[
            "Neon separates compute and storage using page servers",
            "supports pgvector HNSW indexes for 1024-dimensional embeddings",
            "PgBouncer connection pooling handles concurrent connections",
        ],
        relevant_keywords=["pgvector", "compute", "storage", "pgbouncer"],
        evidence=evidence,
        generated_answer=(
            "Neon separates compute and storage using multi-tenant page servers and supports "
            "pgvector HNSW indexes for 1024-dimensional embeddings [S1]. Additionally, PgBouncer "
            "connection pooling handles up to 10,000 concurrent connections in transaction mode [S2]."
        ),
    )

    report = run_evaluation_suite([case])
    assert report.case_count == 1
    assert report.mean_context_precision >= 0.9
    assert report.mean_context_recall >= 0.9
    assert report.mean_answer_faithfulness >= 0.85
    assert report.mean_answer_relevance >= 0.5
    assert report.mean_citation_accuracy == 1.0
    assert report.overall_score >= 0.8
