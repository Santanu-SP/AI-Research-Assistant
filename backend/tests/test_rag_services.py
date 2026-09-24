from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.core.errors import AppError
from app.schemas.rag import EvidenceItem
from app.schemas.retrieval import RetrievalCandidate
from app.services.citations import CitationValidator
from app.services.evidence import EvidenceBuilder, evidence_is_sufficient
from app.services.generation import GenerationService, build_grounding_prompt
from app.services.reranking import RerankerService


def candidate(index: int, *, chunk_id=None) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id or uuid4(),
        document_id=uuid4(),
        paper_title=f"Paper {index}",
        authors=["Researcher"],
        doi=None,
        page=index + 1,
        section=f"Section {index}",
        text=f"Evidence passage {index}",
        vector_score=0.8,
        keyword_score=0.4,
        hybrid_score=0.03,
    )


def evidence(source_id: str = "S1") -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        document_id=uuid4(),
        chunk_id=uuid4(),
        paper_title="Test paper",
        authors=["A. Author"],
        doi="10.1000/test",
        page=4,
        section="Results",
        text="The test system is blue.",
        rerank_score=4.2,
    )


def test_reranker_preserves_metadata_and_sorts_stably() -> None:
    items = [candidate(0), candidate(1), candidate(2)]
    service = RerankerService("Qwen/Qwen3-Reranker-0.6B", batch_size=8)
    service._model = SimpleNamespace(
        predict=lambda pairs, **kwargs: [0.2, 3.5, 0.2]
    )

    ranked = service.rerank("test query", items)

    assert [item.chunk_id for item in ranked] == [
        items[1].chunk_id,
        items[0].chunk_id,
        items[2].chunk_id,
    ]
    assert ranked[0].paper_title == items[1].paper_title
    assert ranked[0].hybrid_score == items[1].hybrid_score
    assert ranked[0].rerank_score == 3.5


def test_evidence_builder_limits_deduplicates_and_assigns_source_ids() -> None:
    duplicate_id = uuid4()
    items = [candidate(0, chunk_id=duplicate_id), candidate(1, chunk_id=duplicate_id), candidate(2)]
    scored = [item.model_copy(update={"rerank_score": 5.0 - index}) for index, item in enumerate(items)]

    built = EvidenceBuilder().build(scored, limit=2)

    assert [item.source_id for item in built] == ["S1", "S2"]
    assert [item.chunk_id for item in built] == [duplicate_id, items[2].chunk_id]
    assert evidence_is_sufficient(built, minimum_count=2, minimum_relevance=1.0)
    assert not evidence_is_sufficient(built, minimum_count=3, minimum_relevance=1.0)


def test_grounding_prompt_contains_only_supplied_evidence_and_rules() -> None:
    prompt = build_grounding_prompt("What color?", [evidence()])

    assert "The test system is blue." in prompt
    assert "What color?" in prompt
    assert "Use only the supplied evidence" in prompt
    assert "outside or pretrained knowledge" in prompt


def test_citation_validator_removes_unknown_ids_and_builds_real_metadata() -> None:
    item = evidence()
    result = CitationValidator().validate("Blue [S1], unsupported [S99].", [item])

    assert result.answer == "Blue [S1], unsupported."
    assert len(result.citations) == 1
    assert result.citations[0].citation_id == "S1"
    assert result.citations[0].chunk_id == item.chunk_id
    assert result.citations[0].excerpt == item.text


def test_generation_service_verifies_model_and_calls_ollama() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        return httpx.Response(200, json={"response": "Blue [S1]."})

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    service = GenerationService(
        base_url="http://ollama.test",
        model_name="qwen3.5:9b",
        max_new_tokens=128,
        temperature=0.1,
        timeout_seconds=10,
        client=client,
    )

    assert service.generate("What color?", [evidence()]) == "Blue [S1]."
    assert [request.url.path for request in requests] == ["/api/tags", "/api/generate"]
    assert b'"model":"qwen3.5:9b"' in requests[1].content


def test_generation_service_reports_missing_model() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"models": []})
        ),
    )
    service = GenerationService(
        base_url="http://ollama.test",
        model_name="qwen3.5:9b",
        max_new_tokens=128,
        temperature=0.1,
        timeout_seconds=10,
        client=client,
    )

    with pytest.raises(AppError) as error:
        service.generate("Question", [evidence()])
    assert error.value.code == "generation_model_missing"


def test_generation_service_reports_ollama_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    service = GenerationService(
        base_url="http://ollama.test",
        model_name="qwen3.5:9b",
        max_new_tokens=128,
        temperature=0.1,
        timeout_seconds=10,
        client=client,
    )

    with pytest.raises(AppError) as error:
        service.generate("Question", [evidence()])
    assert error.value.code == "ollama_unavailable"
