"""Answer quality: citations, prompt layout, query clean-up and evidence size."""

from __future__ import annotations

from uuid import uuid4

from app.core.config import Settings
from app.schemas.rag import EvidenceItem
from app.schemas.retrieval import RetrievalCandidate
from app.services.rag.citations import (
    CitationValidator,
    citation_coverage,
    split_grouped_citations,
    tidy_answer_lines,
)
from app.services.rag.evidence import EvidenceBuilder
from app.services.rag.generation import answer_format_hint, build_grounding_prompt
from app.services.rag.query import build_evidence, resolve_execution_profile
from app.services.rag.reranking import rerank_text
from app.services.rag.retrieval import search_text_for


def _evidence(source_id: str, text: str = "Agent A signs the card.") -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        document_id=uuid4(),
        chunk_id=uuid4(),
        paper_title="Design doc",
        authors=None,
        doi=None,
        page=None,
        section="7. A2A Delegation Workflow",
        section_path=["HLD", "Architecture Explanation", "7. A2A Delegation Workflow"],
        text=text,
        rerank_score=1.0,
    )


def _candidate(text: str, score: float | None, *, section_path=None) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        paper_title="Design doc",
        authors=None,
        doi=None,
        page=None,
        section=(section_path or [None])[-1],
        section_path=section_path,
        text=text,
        hybrid_score=0.03,
        rerank_score=score,
    )


# --- grouped citations -------------------------------------------------------


def test_grouped_citations_are_split() -> None:
    assert split_grouped_citations("Signed cards [S1, S5, S8].") == "Signed cards [S1][S5][S8]."
    assert split_grouped_citations("Steps [S2-S4] and [S1; S3]") == "Steps [S2][S3][S4] and [S1][S3]"
    assert split_grouped_citations("Twice [S1][S1] here") == "Twice [S1] here"
    # Silly ranges are not blown up into dozens of markers.
    assert split_grouped_citations("[S1-S99]") == "[S1]"


def test_validator_checks_every_source_in_a_group() -> None:
    evidence = [_evidence("S1"), _evidence("S2")]
    result = CitationValidator().validate("Agent A signs it [S1, S2, S9].", evidence)
    assert result.answer == "Agent A signs it [S1][S2]."
    assert [c.citation_id for c in result.citations] == ["S1", "S2"]
    assert result.cited_claims == 1 and result.total_claims == 1


def test_citation_coverage_counts_each_sentence_and_list_item() -> None:
    answer = (
        "**Workflow:**\n"
        "1. Agent A creates a signed delegation [S1].\n"
        "2. The handler verifies the signature before accepting.\n"
        "- Invalid signatures block execution of the task [S2]. Results are audited later."
    )
    assert citation_coverage(answer) == (2, 4)
    result = CitationValidator().validate(answer, [_evidence("S1"), _evidence("S2")])
    assert result.coverage == 0.5


def test_tidy_answer_lines_drops_repeats_and_double_markers() -> None:
    answer = (
        "1. Agent A creates the delegation [S1].\n"
        "- 2. Handler verifies the signature [S2].\n"
        "1. Agent A creates the delegation [S1]."
    )
    assert tidy_answer_lines(answer).split("\n") == [
        "1. Agent A creates the delegation [S1].",
        "2. Handler verifies the signature [S2].",
    ]


# --- prompt -----------------------------------------------------------------


def test_format_hint_matches_question_type() -> None:
    assert "numbered steps" in answer_format_hint(
        "How will A2A delegation takes place in the project?"
    )
    assert "bullet list" in answer_format_hint("Which tables store A2A data?")
    assert "short sentences" in answer_format_hint("Who wrote the report?")


def test_prompt_asks_for_separate_citations_and_shows_section_path() -> None:
    prompt = build_grounding_prompt(
        "How does A2A delegation work?", [_evidence("S1")]
    )
    assert "never group" in prompt.lower()
    assert "Answer format:" in prompt
    assert 'section="HLD > Architecture Explanation > 7. A2A Delegation Workflow"' in prompt


# --- query clean-up ---------------------------------------------------------


def test_search_text_drops_pointers_to_the_documents() -> None:
    assert (
        search_text_for("How will A2A delegation takes place in the project in the source documents?")
        == "How will A2A delegation takes place in the project?"
    )
    assert search_text_for("According to the files, what is MCP?") == "what is MCP?"
    # "docs" here is part of the question, so it stays.
    assert search_text_for("What is in the docs folder?") == "What is in the docs folder?"


def test_reranker_sees_the_heading_path() -> None:
    item = _candidate(
        "Agent A creates a signed task.",
        1.0,
        section_path=["HLD", "7. A2A Delegation Workflow"],
    )
    assert rerank_text(item).startswith("HLD > 7. A2A Delegation Workflow\n")
    assert rerank_text(_candidate("Plain text.", 1.0)) == "Plain text."


# --- evidence size ----------------------------------------------------------


def test_evidence_tops_up_short_chunks_within_budget() -> None:
    ranked = [_candidate(f"short chunk number {i} " * 5, 1.0 - i / 100) for i in range(10)]
    fixed = EvidenceBuilder().build(ranked, limit=3)
    topped = EvidenceBuilder().build(ranked, limit=3, char_budget=500, max_items=8)
    assert len(fixed) == 3
    assert 3 < len(topped) <= 8
    assert sum(len(item.text) for item in topped[:-1]) < 500
    assert [item.source_id for item in topped] == [f"S{i}" for i in range(1, len(topped) + 1)]


def test_evidence_top_up_skips_low_scores_and_duplicate_text() -> None:
    ranked = [
        _candidate("first", 2.0),
        _candidate("first", 1.9),
        _candidate("second", 1.5),
        _candidate("weak", -3.0),
    ]
    built = EvidenceBuilder().build(
        ranked, limit=1, char_budget=10_000, max_items=10, min_extra_score=0.0
    )
    assert [item.text for item in built] == ["first", "second"]


def test_deep_reads_more_than_standard() -> None:
    settings = Settings(_env_file=None)
    question = "Explain the full A2A delegation workflow and its failure handling in detail"
    standard = resolve_execution_profile(question, "standard", settings)
    deep = resolve_execution_profile(question, "deep", settings)
    assert deep.settings.evidence_char_budget > standard.settings.evidence_char_budget
    assert deep.settings.evidence_max_items >= standard.settings.evidence_max_items
    ranked = [_candidate(f"chunk {i} " * 30, 1.0) for i in range(30)]
    assert len(build_evidence(ranked, deep.settings, deep.mode)) > len(
        build_evidence(ranked, standard.settings, standard.mode)
    )
    quick = resolve_execution_profile(question, "quick", settings)
    assert len(build_evidence(ranked, quick.settings, quick.mode)) == quick.settings.final_context_k


def test_citation_after_full_stop_counts_for_that_sentence() -> None:
    answer = "1. Agent A signs the delegation card. [S1][S2]\n2. Agent B runs the task and returns it. [S2]"
    result = CitationValidator().validate(answer, [_evidence("S1"), _evidence("S2")])
    assert result.answer.split("\n") == [
        "1. Agent A signs the delegation card [S1][S2].",
        "2. Agent B runs the task and returns it [S2].",
    ]
    assert (result.cited_claims, result.total_claims) == (2, 2)


def test_not_covered_note_is_not_a_claim() -> None:
    answer = "Agent A signs the card first [S1].\n- Not covered in the sources: the key rotation schedule."
    assert citation_coverage(answer) == (1, 1)
