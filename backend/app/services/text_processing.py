from dataclasses import dataclass
import re
from uuid import UUID, uuid4

from app.services.pdf_extraction import ExtractedPage


CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
BROKEN_WORD = re.compile(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])")
HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+\S+", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedChunk:
    id: UUID
    document_id: UUID
    text: str
    page: int
    section: str | None
    chunk_index: int


def normalize_text(text: str) -> str:
    """Remove extraction noise without rewriting scientific notation or symbols."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ").replace("\u00ad", "")
    normalized = CONTROL_CHARACTERS.sub("", normalized)
    normalized = BROKEN_WORD.sub("", normalized)
    lines = [
        HORIZONTAL_WHITESPACE.sub(" ", line).strip()
        for line in normalized.split("\n")
    ]

    rebuilt: list[str] = []
    for line in lines:
        if not line:
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            continue
        if (
            rebuilt
            and rebuilt[-1]
            and not _is_heading(rebuilt[-1])
            and rebuilt[-1][-1] not in ".:;!?)]}"
            and line[0].islower()
        ):
            rebuilt[-1] = f"{rebuilt[-1]} {line}"
        else:
            rebuilt.append(line)

    return EXCESS_BLANK_LINES.sub("\n\n", "\n".join(rebuilt)).strip()


def _is_heading(line: str) -> bool:
    words = line.split()
    if not 1 <= len(words) <= 16 or len(line) > 160:
        return False
    return bool(HEADING_NUMBER.match(line)) or (
        line.isupper() and any(character.isalpha() for character in line)
    )


def _find_section(text: str, current: str | None) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if _is_heading(stripped):
            return stripped
    return current


def _split_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(start + chunk_size, len(text))
        end = hard_end
        if hard_end < len(text):
            preferred = max(
                text.rfind("\n\n", start, hard_end),
                text.rfind(". ", start, hard_end),
            )
            if preferred > start + chunk_size // 2:
                separator = text[preferred : preferred + 2]
                end = preferred + (2 if separator in {"\n\n", ". "} else 0)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_pages(
    document_id: UUID,
    pages: list[ExtractedPage],
    *,
    chunk_size: int,
    overlap: int,
) -> list[PreparedChunk]:
    chunks: list[PreparedChunk] = []
    section: str | None = None
    for page in pages:
        normalized = normalize_text(page.text)
        if not normalized:
            continue
        section = _find_section(normalized, section)
        for text in _split_with_overlap(normalized, chunk_size, overlap):
            chunks.append(
                PreparedChunk(
                    id=uuid4(),
                    document_id=document_id,
                    text=text,
                    page=page.page,
                    section=section,
                    chunk_index=len(chunks),
                )
            )
    return chunks
