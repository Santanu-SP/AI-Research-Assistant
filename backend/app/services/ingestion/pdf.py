from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError


DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


class PdfExtractionError(Exception):
    """A safe, expected failure while reading an uploaded PDF."""


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    text: str


@dataclass(frozen=True)
class ExtractedPdf:
    pages: list[ExtractedPage]
    title: str | None
    authors: list[str] | None
    doi: str | None
    page_count: int


def _clean_metadata_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def extract_doi_from_text(candidates: list[str]) -> str | None:
    """Return the first normalized DOI found across candidate text fragments."""
    for candidate in candidates:
        match = DOI_PATTERN.search(candidate)
        if match:
            return match.group(0).rstrip(".,;)")
    return None


def _extract_doi(reader: PdfReader, pages: list[ExtractedPage]) -> str | None:
    metadata = reader.metadata
    candidates: list[str] = []
    if metadata:
        for key in ("/doi", "/DOI", "/Subject"):
            value = _clean_metadata_value(metadata.get(key))
            if value:
                candidates.append(value)
    candidates.extend(page.text for page in pages[:2])
    return extract_doi_from_text(candidates)


def find_scanned_pdf_pages(
    path: Path,
    pages: list[ExtractedPage],
    *,
    min_chars: int = 40,
    min_text_ratio: float = 0.8,
) -> list[int]:
    """Return 1-based page numbers that lack a usable text layer and warrant OCR."""
    if not pages:
        return []
    low_text_pages = [
        page.page for page in pages if len("".join(page.text.split())) < min_chars
    ]
    if not low_text_pages:
        return []

    pages_with_text = len(pages) - len(low_text_pages)
    doc_has_text_layer = (pages_with_text / len(pages)) >= min_text_ratio
    if not doc_has_text_layer:
        return low_text_pages

    # For predominantly digital PDFs, only OCR sparse pages that contain embedded raster images
    # so blank separator pages never incur extra OCR calls.
    try:
        reader = PdfReader(path, strict=False)
    except Exception:
        return low_text_pages

    ocr_targets: list[int] = []
    for page_num in low_text_pages:
        if page_num < 1 or page_num > len(reader.pages):
            continue
        try:
            if getattr(reader.pages[page_num - 1], "images", None):
                ocr_targets.append(page_num)
        except Exception:
            ocr_targets.append(page_num)
    return ocr_targets


def slice_pdf_pages(path: Path, page_numbers: list[int]) -> bytes:
    """Extract a subset of 1-based pages into minimal in-memory PDF bytes for cloud OCR."""
    reader = PdfReader(path, strict=False)
    writer = PdfWriter()
    for page_num in page_numbers:
        if 1 <= page_num <= len(reader.pages):
            writer.add_page(reader.pages[page_num - 1])
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def pdf_has_text_layer(
    path: Path,
    *,
    sample_pages: int = 12,
    min_chars: int = 40,
    min_ratio: float = 0.8,
) -> bool:
    """True when most sampled pages already contain selectable text.

    Such PDFs (exported from Word, Docs, a browser...) gain nothing from OCR,
    which is the slowest part of reading a document. Scanned PDFs have
    little or no text layer, so they still get OCR. Any read error returns
    False, which keeps OCR on.
    """
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            return False
        total = len(reader.pages)
        if total == 0:
            return False
        count = min(sample_pages, total)
        indexes = sorted({round(i * (total - 1) / max(count - 1, 1)) for i in range(count)})
        with_text = 0
        for index in indexes:
            text = reader.pages[index].extract_text() or ""
            if len("".join(text.split())) >= min_chars:
                with_text += 1
        return with_text / len(indexes) >= min_ratio
    except Exception:
        return False


def extract_pdf(path: Path, *, allow_empty: bool = False) -> ExtractedPdf:
    """Extract page-aware text and only metadata explicitly present in the PDF."""

    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise PdfExtractionError("Password-protected PDFs are not supported")
        if not reader.pages:
            raise PdfExtractionError("The PDF contains no pages")

        pages = [
            ExtractedPage(page=index, text=page.extract_text() or "")
            for index, page in enumerate(reader.pages, start=1)
        ]
        if not allow_empty and not any(page.text.strip() for page in pages):
            raise PdfExtractionError("The PDF contains no extractable text")

        metadata = reader.metadata
        title = _clean_metadata_value(metadata.title) if metadata else None
        author = _clean_metadata_value(metadata.author) if metadata else None
        authors = [author] if author else None

        return ExtractedPdf(
            pages=pages,
            title=title,
            authors=authors,
            doi=_extract_doi(reader, pages),
            page_count=len(pages),
        )
    except PdfExtractionError:
        raise
    except (
        PyPdfError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        UnicodeError,
    ) as exc:
        raise PdfExtractionError("The PDF is corrupted or cannot be read") from exc
