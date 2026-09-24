from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Source
from app.models.research import Research
from app.schemas.retrieval import RetrievalCandidate
from app.services import rag as rag_service


def candidates() -> list[RetrievalCandidate]:
    return [
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            paper_title="First uploaded paper",
            authors=["A. Researcher"],
            doi="10.1000/first",
            page=3,
            section="Findings",
            text="The intervention improved the measured outcome.",
            vector_score=0.9,
            keyword_score=0.5,
            hybrid_score=0.03,
        ),
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            paper_title="Second uploaded paper",
            authors=None,
            doi=None,
            page=7,
            section=None,
            text="The follow-up study reported a similar improvement.",
            vector_score=0.8,
            keyword_score=0.4,
            hybrid_score=0.02,
        ),
    ]


class FakeReranker:
    def __init__(self, score: float = 5.0) -> None:
        self.score = score

    def rerank(self, query, items):
        return [
            item.model_copy(update={"rerank_score": self.score - index})
            for index, item in enumerate(items)
        ]


class FakeGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, question, evidence):
        self.calls += 1
        assert len(evidence) == 2
        return "The studies report improvement [S1] [S2]. Invalid [S99]."


def install_pipeline_fakes(monkeypatch, items, *, score=5.0):
    generator = FakeGenerator()
    captured_user_ids = []

    def fake_retrieve(session, user_id, query, settings):
        captured_user_ids.append(user_id)
        return items

    monkeypatch.setattr(rag_service.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        rag_service, "reranker_service_for", lambda settings: FakeReranker(score)
    )
    monkeypatch.setattr(
        rag_service, "generation_service_for", lambda settings: generator
    )
    return generator, captured_user_ids


def test_query_endpoint_persists_grounded_multi_source_report(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    items = candidates()
    generator, captured_user_ids = install_pipeline_fakes(monkeypatch, items)

    response = client.post(
        "/api/v1/research/query",
        json={"query": "What does the evidence show?", "researchDepth": "standard"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["answer"] == "The studies report improvement [S1] [S2]. Invalid."
    assert body["hybridCandidateCount"] == 2
    assert body["evidenceCount"] == 2
    assert [item["citationId"] for item in body["citations"]] == ["S1", "S2"]
    assert generator.calls == 1
    assert len(captured_user_ids) == 1

    research_id = UUID(body["researchId"])
    record = db_session.get(Research, research_id)
    assert record is not None and record.status.value == "completed"
    sources = list(
        db_session.scalars(
            select(Source).where(Source.research_id == research_id).order_by(Source.number)
        )
    )
    assert [source.document_id for source in sources] == [
        items[0].document_id,
        items[1].document_id,
    ]
    assert sources[0].chunk_id == items[0].chunk_id
    assert sources[0].page == 3
    assert sources[0].rerank_score == 5.0

    report = client.get(f"/api/v1/research/{research_id}/report")
    assert report.status_code == 200
    assert report.json()["report"]["status"] == "completed"
    assert len(report.json()["sources"]) == 2


def test_insufficient_evidence_is_completed_without_generation(
    client: TestClient,
    monkeypatch,
) -> None:
    generator, _ = install_pipeline_fakes(monkeypatch, candidates(), score=-5.0)

    response = client.post(
        "/api/v1/research/query",
        json={"query": "An unsupported question"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["insufficientEvidence"] is True
    assert body["citations"] == []
    assert "do not contain enough relevant evidence" in body["answer"]
    assert generator.calls == 0


def test_query_endpoint_passes_only_authenticated_user_to_retrieval(
    client: TestClient,
    monkeypatch,
) -> None:
    _, captured_user_ids = install_pipeline_fakes(monkeypatch, [])
    me = client.get("/api/v1/auth/me").json()

    response = client.post("/api/v1/research/query", json={"query": "No matches"})

    assert response.status_code == 201
    assert captured_user_ids == [UUID(me["id"])]
    assert response.json()["hybridCandidateCount"] == 0
