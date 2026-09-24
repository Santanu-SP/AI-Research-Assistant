"""Validate model-emitted source references against request-local evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.rag import EvidenceItem, ValidatedCitation


SOURCE_REFERENCE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)


@dataclass(frozen=True)
class CitationValidationResult:
    answer: str
    citations: list[ValidatedCitation]


class CitationValidator:
    def validate(
        self,
        answer: str,
        evidence: list[EvidenceItem],
    ) -> CitationValidationResult:
        evidence_by_id = {item.source_id.upper(): item for item in evidence}
        cited_ids: list[str] = []

        def replace_reference(match: re.Match[str]) -> str:
            source_id = f"S{int(match.group(1))}"
            if source_id not in evidence_by_id:
                return ""
            if source_id not in cited_ids:
                cited_ids.append(source_id)
            return f"[{source_id}]"

        sanitized = SOURCE_REFERENCE.sub(replace_reference, answer)
        sanitized = re.sub(r"[ \t]+([,.;:!?])", r"\1", sanitized)
        sanitized = re.sub(r" {2,}", " ", sanitized).strip()
        citations = [self._citation(evidence_by_id[source_id]) for source_id in cited_ids]
        return CitationValidationResult(answer=sanitized, citations=citations)

    @staticmethod
    def _citation(evidence: EvidenceItem) -> ValidatedCitation:
        return ValidatedCitation(
            citation_id=evidence.source_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            paper_title=evidence.paper_title,
            authors=evidence.authors,
            doi=evidence.doi,
            page=evidence.page,
            section=evidence.section,
            excerpt=evidence.text,
        )
