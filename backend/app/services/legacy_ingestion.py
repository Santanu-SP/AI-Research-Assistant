"""Retained pypdf ingestion adapter for controlled fallback and regression."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion import DocumentIngestionError, stable_node_id
from app.services.pdf_extraction import PdfExtractionError, extract_pdf
from app.services.text_processing import chunk_pages


class LegacyPdfIngestionAdapter:
    """Map the original pypdf pipeline into the canonical ingestion contract."""

    def __init__(self, settings: Settings) -> None:
        self._chunk_size = settings.document_chunk_size
        self._overlap = settings.document_chunk_overlap

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        if path.suffix.lower() != ".pdf":
            raise DocumentIngestionError(
                "The legacy ingestion fallback supports PDF documents only"
            )
        try:
            extracted = extract_pdf(path)
        except PdfExtractionError as exc:
            raise DocumentIngestionError(
                str(exc),
                code="pdf_processing_failed",
            ) from exc

        chunks = chunk_pages(
            document_id,
            extracted.pages,
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
                metadata={"content_kind": "text", "legacy_parser": True},
            )
            for chunk in chunks
        ]
        provenance = {}
        if extracted.title:
            provenance["title"] = MetadataProvenance.EXTRACTED
        if extracted.authors:
            provenance["authors"] = MetadataProvenance.EXTRACTED
        if extracted.doi:
            provenance["doi"] = MetadataProvenance.EXTRACTED
        try:
            parser_version = version("pypdf")
        except PackageNotFoundError:
            parser_version = None
        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=extracted.title,
                authors=extracted.authors,
                doi=extracted.doi,
                values={"legacy_chunking": True},
                provenance=provenance,
            ),
            page_count=extracted.page_count,
            parser_name="pypdf",
            parser_version=parser_version,
            ingestion_version=f"{ingestion_version}:legacy-pdf",
            nodes=nodes,
        )
