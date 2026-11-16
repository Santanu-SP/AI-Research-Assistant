"""Validate model-emitted source references against request-local evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.rag import EvidenceItem, ValidatedCitation


SOURCE_REFERENCE = re.compile(r"\[S(\d+)\]", re.IGNORECASE)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
# Models often group sources: [S1, S5, S8], [S1; S2], [S2-S4], [S1 and S3].
# Those slip past the [S1] pattern, so they were never checked and showed up
# raw in the answer. Split them into [S1][S5][S8] first.
_GROUPED_REFERENCE = re.compile(
    r"\[\s*S\d+(?:\s*(?:,|;|&|and|-|–|to)\s*S?\d+)+\s*\]",
    re.IGNORECASE,
)
_GROUP_PART = re.compile(r"S?(\d+)(?:\s*(?:-|–|to)\s*S?(\d+))?", re.IGNORECASE)
_REPEATED_REFERENCE = re.compile(r"(\[S\d+\])(?:\s*\1)+", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MAX_RANGE = 12
# "...is verified. [S2]" puts the source after the full stop, where it reads
# like the start of the next sentence. Move it in front: "...is verified [S2]."
_CITATION_AFTER_STOP = re.compile(r"([.!?])((?:[ \t]*\[S\d+\])+)(?=\s|$)", re.IGNORECASE)
_NOT_COVERED = re.compile(r"^\W*not covered in the sources\b", re.IGNORECASE)


def split_grouped_citations(answer: str) -> str:
    """Rewrite [S1, S5] and [S2-S4] as [S1][S5] and [S2][S3][S4]."""

    def expand(match: re.Match[str]) -> str:
        numbers: list[int] = []
        for part in _GROUP_PART.finditer(match.group(0)[1:-1]):
            start = int(part.group(1))
            end = int(part.group(2)) if part.group(2) else start
            if end < start or end - start > _MAX_RANGE:
                end = start
            for number in range(start, end + 1):
                if number not in numbers:
                    numbers.append(number)
        return "".join(f"[S{number}]" for number in numbers)

    expanded = _GROUPED_REFERENCE.sub(expand, answer)
    return _REPEATED_REFERENCE.sub(r"\1", expanded)


def attach_trailing_citations(answer: str) -> str:
    """Move markers written after a full stop to before it."""

    def move(match: re.Match[str]) -> str:
        markers = "".join(f"[S{number}]" for number in SOURCE_REFERENCE.findall(match.group(2)))
        return f" {markers}{match.group(1)}"

    return _CITATION_AFTER_STOP.sub(move, answer)


def tidy_answer_lines(answer: str) -> str:
    """Remove lines the model repeated and fix doubled list markers.

    Smaller models sometimes loop and write the same steps several times, or
    write "- 1. Step"; both make the answer look broken.
    """
    seen: set[str] = set()
    lines: list[str] = []
    for line in answer.split("\n"):
        line = re.sub(r"^(\s*)[-*+]\s+(\d+[.)]\s+)", r"\1\2", line)
        key = " ".join(SOURCE_REFERENCE.sub("", line).split()).lower()
        if key and len(key) > 12:
            if key in seen:
                continue
            seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def _is_claim(sentence: str) -> bool:
    """Whether a piece of the answer states something that needs a source.

    Headings, labels ending in ":" and very short fragments are structure,
    not claims.
    """
    text = _LIST_MARKER.sub("", SOURCE_REFERENCE.sub("", sentence)).strip()
    if not text or text.startswith("#") or text.endswith(":"):
        return False
    if _NOT_COVERED.match(text):
        # The "what the sources do not say" note has nothing to cite.
        return False
    if re.fullmatch(r"\*\*[^*]+\*\*:?", text):
        return False
    return len(re.findall(r"[A-Za-z0-9]+", text)) >= 4


def citation_coverage(answer: str) -> tuple[int, int]:
    """Return (claims with a citation, all claims) for an answer."""
    cited = total = 0
    for line in attach_trailing_citations(answer).split("\n"):
        for sentence in SENTENCE_BOUNDARY.split(line):
            if not _is_claim(sentence):
                continue
            total += 1
            if SOURCE_REFERENCE.search(sentence):
                cited += 1
    return cited, total


@dataclass(frozen=True)
class CitationValidationResult:
    answer: str
    citations: list[ValidatedCitation]
    cited_claims: int = 0
    total_claims: int = 0

    @property
    def coverage(self) -> float:
        """Share of claims that carry a valid citation (1.0 when there are none)."""
        return 1.0 if self.total_claims == 0 else self.cited_claims / self.total_claims


class CitationValidator:
    def validate(
        self,
        answer: str,
        evidence: list[EvidenceItem],
    ) -> CitationValidationResult:
        evidence_by_id = {item.source_id.upper(): item for item in evidence}
        cited_ids: list[str] = []
        answer = attach_trailing_citations(split_grouped_citations(answer))

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
        sanitized = tidy_answer_lines(_REPEATED_REFERENCE.sub(r"\1", sanitized))
        sanitized = re.sub(r"[ \t]+([,.;:!?])", r"\1", sanitized)
        sanitized = re.sub(r" {2,}", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        citations = [self._citation(evidence_by_id[source_id]) for source_id in cited_ids]
        cited_claims, total_claims = citation_coverage(sanitized)
        return CitationValidationResult(
            answer=sanitized,
            citations=citations,
            cited_claims=cited_claims,
            total_claims=total_claims,
        )

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
