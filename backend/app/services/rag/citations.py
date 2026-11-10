"""Validate model-emitted source references against request-local evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.rag import EvidenceItem, ValidatedCitation


SOURCE_REFERENCE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


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

        kept_lines = []
        for line in answer.split("\n"):
            kept_sentences = []
            for sentence in SENTENCE_BOUNDARY.split(line):
                markers = SOURCE_REFERENCE.findall(sentence)
                if markers and not any(
                    f"S{int(number)}" in evidence_by_id for number in markers
                ):
                    # Every source this sentence cites is invented, so the
                    # claim is not grounded in the evidence: drop it.
                    continue
                kept_sentences.append(SOURCE_REFERENCE.sub(replace_reference, sentence))
            kept_lines.append(" ".join(part for part in kept_sentences if part.strip()))
        sanitized = "\n".join(kept_lines)
        sanitized = re.sub(r"[ \t]+([,.;:!?])", r"\1", sanitized)
        sanitized = re.sub(r" {2,}", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        citations = [self._citation(evidence_by_id[source_id]) for source_id in cited_ids]
        return CitationValidationResult(answer=sanitized, citations=citations)

    @staticmethod
    def _citation(evidence: EvidenceItem) -> ValidatedCitation:
        return ValidatedCitation(
            citation_id=evidence.source_id,
            node_id=evidence.node_id,
            document_id=evidence.document_id,
            project_id=evidence.project_id,
            source_type=evidence.source_type,
            content_level=evidence.content_level,
            chunk_id=evidence.chunk_id,
            paper_title=evidence.paper_title,
            authors=evidence.authors,
            doi=evidence.doi,
            page=evidence.page,
            page_end=evidence.page_end,
            section=evidence.section,
            section_path=evidence.section_path,
            excerpt=evidence.text,
        )
