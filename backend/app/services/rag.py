"""Orchestration for the authenticated grounded local RAG request."""

from __future__ import annotations

import re
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.reports import SourceType
from app.domain.states import ProjectStatus
from app.schemas.rag import (
    EvidenceItem,
    ResearchQueryRequest,
    ResearchQueryResponse,
    ValidatedCitation,
)
from app.schemas.reports import ResearchReportCreate
from app.schemas.research import ResearchCreate
from app.services import reports, research, retrieval
from app.services.citations import SOURCE_REFERENCE, CitationValidator
from app.services.evidence import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    EvidenceBuilder,
    evidence_is_sufficient,
)
from app.services.generation import GenerationService, generation_service_for
from app.services.reranking import RerankerService, reranker_service_for

WORDS_PER_READING_MINUTE = 200
MIDDLE_DOT = "\u00b7"


def _plain_answer(answer: str) -> str:
    """Strip inline [S#] citation markers and normalize punctuation spacing for display."""
    without_references = SOURCE_REFERENCE.sub("", answer)
    without_reference_spacing = re.sub(
        r"[ \t]+([,.;:!?])", r"\1", without_references
    )
    return re.sub(r" {2,}", " ", without_reference_spacing).strip()


def _report_payload(
    *,
    research_id: UUID,
    title: str,
    answer: str,
    citations: list[ValidatedCitation],
    evidence: list[EvidenceItem],
) -> ResearchReportCreate:
    """Build the atomic ``ResearchReportCreate`` graph from validated RAG citations."""
    evidence_by_id = {item.source_id: item for item in evidence}
    source_payloads = []
    citation_payloads = []

    for position, citation in enumerate(citations):
        source_number = int(citation.citation_id[1:])
        source_uuid = uuid5(research_id, citation.citation_id)
        item = evidence_by_id[citation.citation_id]
        source_payloads.append(
            {
                "id": source_uuid,
                "number": source_number,
                "title": citation.paper_title,
                "publisher": None,
                "authors": citation.authors or [],
                "year": None,
                "sourceType": SourceType.TECHNICAL_REPORT,
                "relevantExcerpt": citation.excerpt,
                "doi": citation.doi,
                "documentId": citation.document_id,
                "chunkId": citation.chunk_id,
                "page": citation.page,
                "section": citation.section,
                "rerankScore": item.rerank_score,
            }
        )
        citation_payloads.append({"sourceId": source_uuid, "position": position})

    display_answer = _plain_answer(answer)
    reading_minutes = max(
        1, len(display_answer.split()) // WORDS_PER_READING_MINUTE + 1
    )
    return ResearchReportCreate(
        title=title,
        summary=display_answer,
        dossier_ref=f"LOCAL RAG {MIDDLE_DOT} {str(research_id)[:8].upper()}",
        reading_time_minutes=reading_minutes,
        sources=source_payloads,
        sections=[
            {
                "heading": "Grounded answer",
                "content": display_answer,
                "position": 0,
                "citations": citation_payloads,
            }
        ],
    )


def run_query(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    settings: Settings,
    *,
    reranker: RerankerService | None = None,
    generator: GenerationService | None = None,
) -> ResearchQueryResponse:
    """Execute the end-to-end grounded RAG pipeline and persist the resulting report."""
    normalized_query = payload.query.strip()
    if not normalized_query:
        raise AppError(
            "A research question is required",
            status_code=422,
            code="research_query_required",
        )

    record = research.create_research(
        session,
        ResearchCreate(
            question=normalized_query,
            project_id=payload.project_id,
            research_depth=payload.research_depth,
        ),
        user_id,
    )
    research.start_research(session, record.id)

    try:
        # Stage 1: Hybrid retrieval (pgvector semantic + PostgreSQL FTS keyword + RRF)
        research.update_research_lifecycle(
            session, record.id, ProjectStatus.PAPERS_SELECTED
        )
        candidates = retrieval.retrieve(
            session,
            user_id,
            normalized_query,
            settings,
            project_id=payload.project_id,
        )
        research.update_progress_counts(
            session,
            record.id,
            sources_discovered=len(candidates),
            sources_reviewed=0,
            documents_found=len({item.document_id for item in candidates}),
        )

        # Stage 2: Cross-encoder reranking and top-k evidence deduplication
        active_reranker = reranker or reranker_service_for(settings)
        ranked = active_reranker.rerank(normalized_query, candidates)
        evidence = EvidenceBuilder().build(ranked, limit=settings.final_context_k)

        research.update_progress_counts(
            session,
            record.id,
            sources_reviewed=len(evidence),
        )
        research.update_research_lifecycle(
            session, record.id, ProjectStatus.RESEARCH_READY
        )

        # Stage 3: Evidence sufficiency verification and grounded generation
        insufficient = not evidence_is_sufficient(
            evidence,
            minimum_count=settings.minimum_evidence_count,
            minimum_relevance=settings.reranker_min_score,
        )
        validator = CitationValidator()
        if insufficient:
            answer = INSUFFICIENT_EVIDENCE_ANSWER
            validated = validator.validate(answer, evidence)
        else:
            research.update_research_lifecycle(
                session, record.id, ProjectStatus.REVIEW_READY
            )
            active_generator = generator or generation_service_for(settings)
            generated = active_generator.generate(normalized_query, evidence)
            validated = validator.validate(generated, evidence)
            answer = validated.answer

        # Stage 4: Persist report dossier and mark research run complete
        reports.persist_report(
            session,
            record.id,
            _report_payload(
                research_id=record.id,
                title=record.title,
                answer=answer,
                citations=validated.citations,
                evidence=evidence,
            ),
        )
        research.mark_research_completed(session, record.id)

        return ResearchQueryResponse(
            research_id=record.id,
            project_id=record.project_id,
            answer=answer,
            citations=validated.citations,
            hybrid_candidate_count=len(candidates),
            evidence_count=len(evidence),
            insufficient_evidence=insufficient,
        )
    except AppError:
        research.mark_research_failed(session, record.id)
        raise
    except Exception as exc:
        research.mark_research_failed(session, record.id)
        raise AppError(
            "The grounded research request could not be completed",
            status_code=500,
            code="research_pipeline_failed",
        ) from exc