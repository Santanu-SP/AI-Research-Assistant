"""Tests for grounded report follow-up Q&A with compact report memory and tiny 0.25x credit cost."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.providers.base import LLMResponse, TokenUsage
from app.schemas.retrieval import RetrievalCandidate
from app.services.rag import query as rag_service


class _LexicalOrderReranker:
    def rerank(self, query: str, items: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        return [
            item.model_copy(update={"rerank_score": 5.0 - idx})
            for idx, item in enumerate(items)
        ]


def test_report_followup_uses_compact_memory_preserves_sources_and_charges_quarter_credit(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch,
) -> None:
    """Four follow-ups cost the same as one full report and include compact memory + grounded citations."""
    settings = test_app.state.settings
    settings.gemini_api_key = "server-gemini-key"
    settings.llm_router_providers = ["gemini"]
    settings.llm_credits_3h_per_model = 20
    settings.llm_credits_2d_per_model = 100

    doc_id = uuid4()
    chunk_1 = RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=doc_id,
        paper_title="Lithium Carbonate Clinical Pharmacology",
        authors=["Dr. A. Sharma"],
        doi="10.1000/lithium",
        page=2,
        section="Mechanism of Action",
        text="Lithium inhibits inositol monophosphatase and modulates GSK-3 beta signaling [S1].",
        vector_score=0.94,
        keyword_score=0.88,
        hybrid_score=0.91,
    )
    chunk_2 = RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=doc_id,
        paper_title="Lithium Carbonate Clinical Pharmacology",
        authors=["Dr. A. Sharma"],
        doi="10.1000/lithium",
        page=4,
        section="Therapeutic Monitoring",
        text="Standard serum lithium maintenance concentrations range from 0.6 to 1.0 mmol/L [S2].",
        vector_score=0.89,
        keyword_score=0.83,
        hybrid_score=0.86,
    )

    retrieval_mode = {"items": [chunk_1]}

    def fake_retrieve(*_args, **_kwargs):
        return list(retrieval_mode["items"])

    monkeypatch.setattr(rag_service.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_service, "reranker_service_for", lambda *_a, **_kw: _LexicalOrderReranker())

    captured_prompts: list[dict[str, object]] = []

    class FollowupStubGenerator:
        def __init__(self, content: str, *, provider: str = "gemini", used_byok: bool = False) -> None:
            self.content = content
            self.provider = provider
            self.used_byok = used_byok
            self.last_response: LLMResponse | None = None

        def generate(self, question: str, evidence, **kwargs) -> str:
            captured_prompts.append(
                {
                    "question": question,
                    "report_memory": kwargs.get("report_memory"),
                    "evidence_ids": [e.source_id for e in evidence],
                }
            )
            self.last_response = LLMResponse(
                provider=self.provider,
                model="gemini-3.8-flash",
                content=self.content,
                usage=TokenUsage(prompt_tokens=90, completion_tokens=30, total_tokens=120),
                used_byok=self.used_byok,
            )
            return self.last_response.content

    # Step 1: Generate initial report -> uses 1.0 credit (20 -> 19 = 95%).
    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: FollowupStubGenerator(
            "Lithium modulates neuronal signaling by inhibiting inositol monophosphatase [S1]."
        ),
    )
    initial = client.post(
        "/api/v1/research/query",
        json={"query": "How does lithium carbonate work?", "researchDepth": "quick"},
    )
    assert initial.status_code == 201, initial.text
    research_id = initial.json()["researchId"]

    usage_after_report = client.get("/api/v1/auth/api-keys/usage").json()
    gemini_after_report = next(
        p for p in usage_after_report["providerCredits"] if p["provider"] == "gemini"
    )
    assert gemini_after_report["remainingPct"] == 95

    # Step 2: Ask 1st follow-up retrieving BOTH chunk_1 (reused [S1]) and chunk_2 (new [S2]).
    retrieval_mode["items"] = [chunk_1, chunk_2]
    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: FollowupStubGenerator(
            "Maintenance serum monitoring typically targets 0.6 to 1.0 mmol/L [S2], alongside GSK-3 inhibition [S1]."
        ),
    )
    res_1 = client.post(
        f"/api/v1/research/{research_id}/followups",
        json={"question": "What serum level should be monitored?"},
    )
    assert res_1.status_code == 201, res_1.text
    body_1 = res_1.json()
    assert body_1["creditCost"] == 0.25
    assert body_1["followup"]["citationIds"] == [2, 1]
    assert len(body_1["sources"]) == 2
    assert captured_prompts[-1]["report_memory"]
    assert "How does lithium carbonate work?" in str(captured_prompts[-1]["report_memory"])
    assert len(str(captured_prompts[-1]["report_memory"])) <= 1500

    # Ask 3 more lightweight follow-ups -> total 4 follow-ups = 1.0 full report (95% -> 90%)!
    for idx in range(3):
        res_n = client.post(
            f"/api/v1/research/{research_id}/followups",
            json={"question": f"Clarify detail {idx}"},
        )
        assert res_n.status_code == 201, res_n.text
        assert res_n.json()["creditCost"] == 0.25

    usage_after_4 = client.get("/api/v1/auth/api-keys/usage").json()
    gemini_after_4 = next(
        p for p in usage_after_4["providerCredits"] if p["provider"] == "gemini"
    )
    assert gemini_after_4["remainingPct"] == 90

    # Step 3: Verify persisted follow-up thread on GET /report includes prior Q&A + newly cited [S2].
    report_res = client.get(f"/api/v1/research/{research_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert len(report_data["followups"]) == 4
    assert report_data["followups"][0]["question"] == "What serum level should be monitored?"
    assert report_data["followups"][0]["position"] == 0
    assert len(report_data["sources"]) == 2
    # Latest follow-up's prompt carried compact memory of prior follow-ups too.
    assert "Earlier follow-up" in str(captured_prompts[-1]["report_memory"])

    # Step 4: Ungrounded follow-up refunds its 0.25x credit and stays at 90%.
    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: FollowupStubGenerator("Uncited speculation without bracket refs."),
    )
    ungrounded = client.post(
        f"/api/v1/research/{research_id}/followups",
        json={"question": "Any ungrounded fact?"},
    )
    assert ungrounded.status_code == 201
    assert ungrounded.json()["creditCost"] == 0.0
    assert ungrounded.json()["followup"]["insufficientEvidence"] is True

    usage_after_refund = client.get("/api/v1/auth/api-keys/usage").json()
    gemini_refunded = next(
        p for p in usage_after_refund["providerCredits"] if p["provider"] == "gemini"
    )
    assert gemini_refunded["remainingPct"] == 90

    # Step 5: BYOK follow-up uses 0 credits (creditCost == 0.0) even with followups active.
    assert client.put(
        "/api/v1/auth/api-keys/openai",
        json={"apiKey": "sk-" + "followup-byok-key"},
    ).status_code == 200
    monkeypatch.setattr(
        rag_service,
        "generation_service_for",
        lambda *_a, **_kw: FollowupStubGenerator(
            "Inhibits inositol monophosphatase [S1].",
            provider="openai",
            used_byok=True,
        ),
    )
    byok_followup = client.post(
        f"/api/v1/research/{research_id}/followups",
        json={"question": "Explain again", "preferredProvider": "openai"},
    )
    assert byok_followup.status_code == 201
    assert byok_followup.json()["creditCost"] == 0.0


def test_alembic_0021_upgrade_and_downgrade_sqlite(tmp_path, monkeypatch) -> None:
    """Verify migration 0021 upgrades cleanly and rolls back without schema drift."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    repo_root = Path(__file__).resolve().parents[2]
    db_url = f"sqlite:///{tmp_path / 'followup_migration.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(repo_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        try:
            insp = inspect(engine)
            assert "report_followups" in insp.get_table_names()
        finally:
            engine.dispose()
        command.downgrade(cfg, "0020_research_discovery_scope")
        engine_down = create_engine(db_url)
        try:
            insp_down = inspect(engine_down)
            assert "report_followups" not in insp_down.get_table_names()
        finally:
            engine_down.dispose()
        command.upgrade(cfg, "head")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
