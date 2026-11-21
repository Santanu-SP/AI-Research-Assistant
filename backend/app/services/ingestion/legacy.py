"""Lightweight zero-ML ingestion adapter with Gemini Flash scanned-PDF OCR fallback."""

from importlib.metadata import PackageNotFoundError, version
import logging
from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id
from app.services.ingestion.pdf import (
    ExtractedPage,
    PdfExtractionError,
    extract_doi_from_text,
    extract_pdf,
    find_scanned_pdf_pages,
)
from app.services.ingestion.text import chunk_pages, normalize_text

logger = logging.getLogger(__name__)


class LegacyPdfIngestionAdapter:
    """Parse PDF (with Gemini Flash scanned-page OCR fallback), DOCX, and TXT without Torch/Docling."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._chunk_size = settings.document_chunk_size
        self._overlap = settings.document_chunk_overlap

    def _parse_plain_text(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise DocumentIngestionError(
                "The text document could not be read",
                code="document_processing_failed",
                status_code=422,
            ) from exc

        cleaned = normalize_text(raw)
        if not cleaned:
            raise DocumentIngestionError(
                "The text document contains no extractable text",
                code="document_processing_failed",
                status_code=422,
            )

        chunks = chunk_pages(
            document_id,
            [ExtractedPage(page=1, text=cleaned)],
            chunk_size=self._chunk_size,
            overlap=self._overlap,
        )
        nodes = [
            ParsedNode(
                node_id=stable_node_id(document_id, chunk.chunk_index, chunk.text),
                text=chunk.text,
                page=None,
                page_end=None,
                section=chunk.section,
                section_path=[chunk.section] if chunk.section else [],
                chunk_index=chunk.chunk_index,
                metadata={"content_kind": "text", "legacy_parser": True},
            )
            for chunk in chunks
        ]
        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=path.stem,
                values={"format": "txt", "legacy_parser": True},
                provenance={"title": MetadataProvenance.EXTRACTED},
            ),
            page_count=1,
            parser_name="plain-text",
            parser_version="1.0",
            ingestion_version=f"{ingestion_version}:legacy-txt",
            nodes=nodes,
        )

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            from app.services.ingestion.office_html import parse_docx_document

            return parse_docx_document(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
                chunk_size=self._chunk_size,
                overlap=self._overlap,
            )
        if suffix == ".txt":
            return self._parse_plain_text(
                path,
                document_id=document_id,
                ingestion_version=ingestion_version,
            )
        if suffix != ".pdf":
            raise DocumentIngestionError(
                "The legacy ingestion fallback supports PDF, DOCX, and TXT documents only"
            )
        try:
            extracted = extract_pdf(path, allow_empty=True)
        except PdfExtractionError as exc:
            raise DocumentIngestionError(
                str(exc),
                code="pdf_processing_failed",
            ) from exc

        pages = list(extracted.pages)
        scanned_pages = find_scanned_pdf_pages(path, pages)
        ocr_pages: set[int] = set()

        if scanned_pages and self._settings.vision_enabled and self._settings.gemini_api_key:
            from app.services.ingestion.vision import vision_analyzer_for

            try:
                ocr_results = vision_analyzer_for(self._settings).ocr_pdf_pages(
                    path, scanned_pages
                )
            except DocumentIngestionError as exc:
                if any(page.text.strip() for page in pages):
                    logger.warning(
                        "Gemini OCR skipped for scanned PDF pages %s; continuing with text pages (%s)",
                        scanned_pages,
                        exc,
                    )
                    ocr_results = {}
                else:
                    raise DocumentIngestionError(
                        str(exc),
                        code="pdf_processing_failed",
                        status_code=exc.status_code,
                    ) from exc
            except Exception as exc:
                if any(page.text.strip() for page in pages):
                    logger.warning(
                        "Unexpected Gemini OCR failure on scanned PDF pages %s; keeping extractable pages",
                        scanned_pages,
                        exc_info=True,
                    )
                    ocr_results = {}
                else:
                    raise DocumentIngestionError(
                        "The scanned PDF could not be processed with Gemini OCR",
                        code="pdf_processing_failed",
                    ) from exc

            if ocr_results:
                updated_pages: list[ExtractedPage] = []
                for page in pages:
                    ocr_text = (ocr_results.get(page.page) or "").strip()
                    if ocr_text:
                        existing = page.text.strip()
                        merged_text = (
                            f"{existing}\n\n{ocr_text}" if existing else ocr_text
                        )
                        updated_pages.append(ExtractedPage(page=page.page, text=merged_text))
                        ocr_pages.add(page.page)
                    else:
                        updated_pages.append(page)
                pages = updated_pages

        if not any(page.text.strip() for page in pages):
            raise DocumentIngestionError(
                "The PDF contains no extractable text",
                code="pdf_processing_failed",
            )

        doi = extracted.doi or extract_doi_from_text([page.text for page in pages[:2]])
        chunks = chunk_pages(
            document_id,
            pages,
            chunk_size=self._chunk_size,
            overlap=self._overlap,
        )
        nodes = [
            ParsedNode(
                node_id=stable_node_id(
                    document_id,
                    chunk.chunk_index,
                    chunk.text,
                ),
                text=chunk.text,
                page=chunk.page,
                page_end=chunk.page,
                section=chunk.section,
                section_path=[chunk.section] if chunk.section else [],
                chunk_index=chunk.chunk_index,
                metadata={
                    "content_kind": "text",
                    "legacy_parser": True,
                    **({"ocr_provider": "gemini-vision"} if chunk.page in ocr_pages else {}),
                },
            )
            for chunk in chunks
        ]
        provenance = {}
        if extracted.title:
            provenance["title"] = MetadataProvenance.EXTRACTED
        if extracted.authors:
            provenance["authors"] = MetadataProvenance.EXTRACTED
        if doi:
            provenance["doi"] = MetadataProvenance.EXTRACTED
        try:
            parser_version = version("pypdf")
        except PackageNotFoundError:
            parser_version = None
        used_ocr = bool(ocr_pages)
        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=extracted.title,
                authors=extracted.authors,
                doi=doi,
                values={
                    "legacy_chunking": True,
                    **({"gemini_pdf_ocr": True, "ocr_pages": sorted(ocr_pages)} if used_ocr else {}),
                },
                provenance=provenance,
            ),
            page_count=extracted.page_count,
            parser_name="pypdf+gemini-ocr" if used_ocr else "pypdf",
            parser_version=parser_version,
            ingestion_version=(
                f"{ingestion_version}:legacy-pdf-ocr"
                if used_ocr
                else f"{ingestion_version}:legacy-pdf"
            ),
            nodes=nodes,
        )
