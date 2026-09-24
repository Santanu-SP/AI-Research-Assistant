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
    ) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        seen_chunks = set()
        for candidate in candidates:
            if len(evidence) >= limit:
                break
            if candidate.chunk_id in seen_chunks or candidate.rerank_score is None:
                continue
            seen_chunks.add(candidate.chunk_id)
            evidence.append(
                EvidenceItem(
                    source_id=f"S{len(evidence) + 1}",
                    document_id=candidate.document_id,
                    chunk_id=candidate.chunk_id,
                    paper_title=candidate.paper_title,
                    authors=candidate.authors,
                    doi=candidate.doi,
                    page=candidate.page,
                    section=candidate.section,
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
