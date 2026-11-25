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


def test_prompt_encourages_plain_english_and_depth_calibrated_hints() -> None:
    quick_hint = answer_format_hint("How does agent handoff work?", depth="quick")
    deep_hint = answer_format_hint("How does agent handoff work?", depth="deep")
    compare_hint = answer_format_hint("Compare REST vs gRPC for transport")

    assert "plain-English" in quick_hint
    assert "endpoints" not in quick_hint
    assert "numbered steps" in deep_hint and "endpoints" in deep_hint
    assert "Markdown table" in compare_hint

    prompt = build_grounding_prompt(
        "Compare REST vs gRPC", [_evidence("S1")], research_depth="quick"
    )
    assert "plain, direct language" in prompt
    assert "Markdown table" in prompt


def test_tidy_normalizes_unicode_bullets_and_preserves_multiple_tables() -> None:
    raw = (
        "###Overview\n"
        "• First bullet item here [S1]\n"
        "  ‣ Nested bullet item stays indented [S1]\n\n"
        "| Option | Summary |\n"
        "| --- | --- |\n"
        "| Alpha | Good for quick checks [S1] |\n\n"
        "###Second table\n"
        "| Option | Summary |\n"
        "| --- | --- |\n"
        "| Beta | Good for deep dives [S1] |"
    )
    cleaned = tidy_answer_lines(raw)
    assert "### Overview" in cleaned
    assert "- First bullet item here [S1]" in cleaned
    assert "  - Nested bullet item stays indented [S1]" in cleaned
    assert cleaned.count("| --- | --- |") == 2
    assert cleaned.count("| Option | Summary |") == 2


def test_citation_validator_handles_markdown_tables_and_nested_indentation() -> None:
    answer = (
        "Here is the summary [S1].\n\n"
        "- Primary step [S1]\n"
        "  - Nested detail stays indented [S1]\n\n"
        "| Feature | Details | Status |\n"
        "| --- | --- | --- |\n"
        "| Delegation | Agent A signs cards [S1] | Active. [S1] |\n"
        "| Fake row | Invented feature [S9] | Unknown [S9] |\n"
        "| Mixed row | Valid note [S1] | Dropped note. [S9] |"
    )
    result = CitationValidator().validate(answer, [_evidence("S1")])
    assert "  - Nested detail stays indented [S1]" in result.answer
    assert "Fake row" not in result.answer
    assert "| Delegation | Agent A signs cards [S1] | Active [S1]. |" in result.answer
    assert "| Mixed row | Valid note [S1] |  |" in result.answer or "| Mixed row | Valid note [S1] | |" in result.answer
    assert result.cited_claims == result.total_claims == 4


def test_validator_deduplicates_same_doc_page_clusters_and_repeated_refs() -> None:
    shared_doc = uuid4()
    other_doc = uuid4()
    same_doc_chunk1 = _evidence("S1", "Chunk 1 text").model_copy(
        update={"document_id": shared_doc, "page": 2}
    )
    same_doc_chunk2 = _evidence("S2", "Chunk 2 text").model_copy(
        update={"document_id": shared_doc, "page": 2}
    )
    same_doc_page5 = _evidence("S3", "Page 5 text").model_copy(
        update={"document_id": shared_doc, "page": 5}
    )
    other_doc_chunk = _evidence("S4", "Other paper").model_copy(
        update={"document_id": other_doc, "page": 1}
    )

    answer = (
        "Delegation [S1] uses signed capability cards [S1][S2][S3][S4].\n"
        "It isolates retries cleanly [S2]."
    )
    # In line 1: earlier [S1] is superseded by sentence-end [S1]; [S2] shares (shared_doc, page 2)
    # with [S1] in the same cluster so it collapses, while [S3] (page 5) and [S4] (other_doc) stay.
    # Line 2 still cites S2 legitimately in its own sentence.
    result = CitationValidator().validate(
        answer, [same_doc_chunk1, same_doc_chunk2, same_doc_page5, other_doc_chunk]
    )
    lines = result.answer.split("\n")
    assert lines[0] == "Delegation uses signed capability cards [S1][S3][S4]."
    assert lines[1] == "It isolates retries cleanly [S2]."
    assert [c.citation_id for c in result.citations] == ["S1", "S3", "S4", "S2"]


def test_split_report_sections_promotes_summary_and_splits_subheadings() -> None:
    from app.services.rag.query import _report_payload, _split_report_sections

    answer = (
        "Lithium calms overactive nerve signaling and needs regular blood tests [S1][S2].\n\n"
        "### **How It Works:**\n"
        "- Slows excessive intracellular cascades [S1].\n\n"
        "### Monitoring & Safety\n"
        "- Check serum levels periodically [S2]."
    )
    summary, sections = _split_report_sections(answer)
    assert summary == "Lithium calms overactive nerve signaling and needs regular blood tests [S1][S2]."
    assert [heading for heading, _ in sections] == ["How It Works", "Monitoring & Safety"]
    assert "Slows excessive intracellular cascades [S1]." in sections[0][1]

    ev1 = _evidence("S1")
    ev2 = _evidence("S2")
    validated = CitationValidator().validate(answer, [ev1, ev2])
    payload = _report_payload(
        research_id=uuid4(),
        title="Lithium overview",
        answer=validated.answer,
        citations=validated.citations,
        evidence=[ev1, ev2],
    )
    assert payload.summary == summary
    assert [sec.heading for sec in payload.sections] == ["How It Works", "Monitoring & Safety"]
    assert len(payload.sections[0].citations) == 1
    assert len(payload.sections[1].citations) == 1


def test_split_report_sections_unwraps_summary_heading_and_keeps_short_flat_answer() -> None:
    from app.services.rag.query import _split_report_sections

    headed = (
        "### Bottom Line\n"
        "Short direct answer [S1].\n\n"
        "### Key Findings\n"
        "- Detail A [S1].\n\n"
        "### Caveats\n"
        "- Detail B [S2]."
    )
    summary, sections = _split_report_sections(headed)
    assert summary == "Short direct answer [S1]."
    assert [heading for heading, _ in sections] == ["Key Findings", "Caveats"]

    flat_short_summary, flat_short_sections = _split_report_sections("One sentence answer [S1].")
    assert flat_short_summary == "One sentence answer [S1]."
    assert flat_short_sections == [("Grounded answer", "One sentence answer [S1].")]
