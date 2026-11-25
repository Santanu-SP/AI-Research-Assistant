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


_TABLE_SEPARATOR = re.compile(
    r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*(?::?-{2,}:?)?\s*\|?\s*$"
)


def _is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR.match(line))


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and "|" in stripped[1:]


def tidy_answer_lines(answer: str) -> str:
    """Normalize bullets/headings and remove duplicate lines emitted by models.

    Smaller models sometimes emit Unicode bullets, omit spaces after `#`
    headings, loop and write the same steps repeatedly, or write "- 1. Step".
    Table separator rows and non-consecutive table rows are preserved so
    multiple tables with similar columns do not get broken.
    """
    seen: set[str] = set()
    lines: list[str] = []
    prev_table_key: str | None = None
    for line in answer.split("\n"):
        line = re.sub(r"^(\s*)[•‣]\s+", r"\1- ", line)
        line = re.sub(r"^(\s*)[-*+]\s+(\d+[.)]\s+)", r"\1\2", line)
        line = re.sub(r"^(#{1,4})([^\s#])", r"\1 \2", line)
        if _is_table_separator(line):
            lines.append(line)
            prev_table_key = None
            continue
        key = " ".join(SOURCE_REFERENCE.sub("", line).split()).lower()
        if _is_table_row(line):
            if key and key == prev_table_key:
                continue
            prev_table_key = key or None
            lines.append(line)
            continue
        prev_table_key = None
        if key and len(key) > 12:
            if key in seen:
                continue
            seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def _is_claim(sentence: str) -> bool:
    """Whether a piece of the answer states something that needs a source.

    Headings, table separators, labels ending in ":" and very short fragments
    are structure, not claims.
    """
    if _is_table_separator(sentence):
        return False
    text = _LIST_MARKER.sub("", SOURCE_REFERENCE.sub("", sentence))
    text = text.replace("|", " ").strip()
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
    lines = attach_trailing_citations(answer).split("\n")
    for idx, line in enumerate(lines):
        if _is_table_separator(line):
            continue
        # Skip Markdown table header rows directly above a separator row.
        if (
            _is_table_row(line)
            and idx + 1 < len(lines)
            and _is_table_separator(lines[idx + 1])
        ):
            continue
        if _is_table_row(line):
            if _is_claim(line):
                total += 1
                if SOURCE_REFERENCE.search(line):
                    cited += 1
            continue
        for sentence in SENTENCE_BOUNDARY.split(line):
            if not _is_claim(sentence):
                continue
            total += 1
            if SOURCE_REFERENCE.search(sentence):
                cited += 1
    return cited, total


_CITATION_CLUSTER = re.compile(r"\[S\d+\](?:[ \t]*\[S\d+\])+", re.IGNORECASE)


def _dedup_citation_cluster(
    sentence: str,
    evidence_by_id: dict[str, EvidenceItem],
) -> str:
    """Drop repeated or same-(document, page) chunk markers within one cluster."""

    def shrink(match: re.Match[str]) -> str:
        cluster = match.group(0)
        tokens = list(SOURCE_REFERENCE.finditer(cluster))
        if len(tokens) <= 1:
            return cluster
        seen_ids: set[str] = set()
        seen_doc_pages: set[tuple[object, object]] = set()
        kept: list[tuple[str, str]] = []
        last_end = 0
        for idx, tok in enumerate(tokens):
            gap = cluster[last_end : tok.start()] if idx > 0 else ""
            last_end = tok.end()
            sid = f"S{int(tok.group(1))}"
            if sid in seen_ids:
                continue
            item = evidence_by_id.get(sid)
            if item is not None and item.document_id is not None:
                doc_page = (item.document_id, item.page)
                if doc_page in seen_doc_pages:
                    continue
                seen_doc_pages.add(doc_page)
            seen_ids.add(sid)
            kept.append((" " if (kept and gap) else "", f"[{sid}]"))
        return "".join(f"{sep}{marker}" for sep, marker in kept)

    return _CITATION_CLUSTER.sub(shrink, sentence)


def _dedup_sentence_repeats(sentence: str) -> str:
    """When the same [S#] repeats across one sentence, keep its final position."""
    matches = list(SOURCE_REFERENCE.finditer(sentence))
    if len(matches) <= 1:
        return sentence
    last_index_by_id: dict[str, int] = {}
    for idx, match in enumerate(matches):
        last_index_by_id[f"S{int(match.group(1))}"] = idx
    parts: list[str] = []
    cursor = 0
    for idx, match in enumerate(matches):
        sid = f"S{int(match.group(1))}"
        parts.append(sentence[cursor : match.start()])
        if last_index_by_id[sid] == idx:
            parts.append(f"[{sid}]")
        cursor = match.end()
    parts.append(sentence[cursor:])
    return "".join(parts)


def _clean_text_segment(
    text: str,
    evidence_by_id: dict[str, EvidenceItem],
    replace_reference,
) -> str:
    kept_sentences = []
    for sentence in SENTENCE_BOUNDARY.split(text):
        markers = SOURCE_REFERENCE.findall(sentence)
        if markers and not any(
            f"S{int(number)}" in evidence_by_id for number in markers
        ):
            # Every source this sentence cites is invented, so the
            # claim is not grounded in the evidence: drop it.
            continue
        cleaned = SOURCE_REFERENCE.sub(replace_reference, sentence)
        cleaned = _dedup_citation_cluster(cleaned, evidence_by_id)
        cleaned = _dedup_sentence_repeats(cleaned)
        kept_sentences.append(cleaned)
    return " ".join(part for part in kept_sentences if part.strip())


def _clean_table_row(
    line: str,
    evidence_by_id: dict[str, EvidenceItem],
    replace_reference,
) -> str | None:
    if _is_table_separator(line):
        return line
    row_markers = SOURCE_REFERENCE.findall(line)
    if row_markers and not any(
        f"S{int(number)}" in evidence_by_id for number in row_markers
    ):
        return None
    stripped = line.strip()
    inner = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
    cleaned_cells = [
        _clean_text_segment(cell.strip(), evidence_by_id, replace_reference).strip()
        for cell in inner.split("|")
    ]
    return f"| {' | '.join(cleaned_cells)} |"


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
        answer = attach_trailing_citations(split_grouped_citations(answer))

        def replace_reference(match: re.Match[str]) -> str:
            source_id = f"S{int(match.group(1))}"
            if source_id not in evidence_by_id:
                return ""
            return f"[{source_id}]"

        kept_lines = []
        for line in answer.split("\n"):
            if _is_table_row(line) or _is_table_separator(line):
                cleaned_row = _clean_table_row(line, evidence_by_id, replace_reference)
                if cleaned_row is not None:
                    kept_lines.append(cleaned_row)
                continue
            kept_lines.append(
                _clean_text_segment(line, evidence_by_id, replace_reference)
            )
        sanitized = "\n".join(kept_lines)
        sanitized = tidy_answer_lines(_REPEATED_REFERENCE.sub(r"\1", sanitized))
        sanitized = re.sub(r"[ \t]+([,.;:!?])", r"\1", sanitized)
        sanitized = re.sub(r"(?<=\S) {2,}", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        cited_ids: list[str] = []
        for number in SOURCE_REFERENCE.findall(sanitized):
            source_id = f"S{int(number)}"
            if source_id in evidence_by_id and source_id not in cited_ids:
                cited_ids.append(source_id)
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
            url=evidence.url,
            publisher=evidence.publisher,
            year=evidence.year,
            page=evidence.page,
            page_end=evidence.page_end,
            section=evidence.section,
            section_path=evidence.section_path,
            excerpt=evidence.text,
        )
