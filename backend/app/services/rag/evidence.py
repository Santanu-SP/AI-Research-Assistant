"""Deterministic final-context construction and explainable sufficiency checks."""

from __future__ import annotations

from app.schemas.rag import EvidenceItem
from app.schemas.retrieval import RetrievalCandidate


INSUFFICIENT_EVIDENCE_ANSWER = (
    "The uploaded sources do not contain enough relevant evidence to answer "
    "this question reliably."
)


class EvidenceBuilder:
    def build(
        self,
        candidates: list[RetrievalCandidate],
        *,
        limit: int,
        char_budget: int = 0,
        max_items: int | None = None,
        min_extra_score: float = 0.0,
    ) -> list[EvidenceItem]:
        """Take the ``limit`` best chunks, then top up while space allows.

        Chunks vary a lot in size: a PDF chunk can be 2,000 characters while a
        DOCX section is often 200. A fixed count therefore gives the model very
        little to read for short-chunk documents. With ``char_budget`` set,
        further relevant chunks (score at least ``min_extra_score``) are added
        until the evidence reaches that many characters or ``max_items``.
        """
        evidence: list[EvidenceItem] = []
        seen_chunks = set()
        seen_texts = set()
        total_chars = 0
        hard_limit = max(limit, max_items or limit)
        for candidate in candidates:
            if len(evidence) >= hard_limit:
                break
            if len(evidence) >= limit and (
                total_chars >= char_budget
                or candidate.rerank_score is None
                or candidate.rerank_score < min_extra_score
            ):
                break
            if candidate.chunk_id in seen_chunks or candidate.rerank_score is None:
                continue
            # The same paragraph can appear in more than one document (or twice
            # in one); sending it again only wastes space.
            text_key = " ".join(candidate.text.split()).lower()
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)
            total_chars += len(candidate.text)
            seen_chunks.add(candidate.chunk_id)
            evidence.append(
                EvidenceItem(
                    source_id=f"S{len(evidence) + 1}",
                    node_id=candidate.node_id,
                    document_id=candidate.document_id,
                    project_id=candidate.project_id,
                    source_type=candidate.source_type,
                    content_level=candidate.content_level,
                    chunk_id=candidate.chunk_id,
                    paper_title=candidate.paper_title,
                    authors=candidate.authors,
                    doi=candidate.doi,
                    url=candidate.url,
                    publisher=candidate.publisher,
                    year=candidate.year,
                    page=candidate.page,
                    page_end=candidate.page_end,
                    section=candidate.section,
                    section_path=candidate.section_path,
                    text=candidate.text,
                    rerank_score=candidate.rerank_score,
                )
            )
        return evidence


def evidence_is_sufficient(
    evidence: list[EvidenceItem],
    *,
    minimum_count: int,
    minimum_relevance: float,
) -> bool:
    return (
        len(evidence) >= minimum_count
        and max((item.rerank_score for item in evidence), default=float("-inf"))
        >= minimum_relevance
    )
