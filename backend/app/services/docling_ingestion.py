"""Official Docling and LlamaIndex adapter for rich local file ingestion."""

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
from typing import Any, Sequence
from uuid import UUID

from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import (
    HuggingFaceTokenizer,
)
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from llama_index.core.schema import BaseNode, Document as LlamaDocument
from llama_index.node_parser.docling import DoclingNodeParser
from llama_index.readers.docling import DoclingReader
from transformers import AutoTokenizer

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion import DocumentIngestionError, stable_node_id


DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    """Keep tables readable for embedding and evidence display."""

    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
        )


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _extract_title(data: dict[str, Any]) -> str | None:
    for item in data.get("texts", []):
        if item.get("label") == "title":
            title = _clean_text(item.get("text"))
            if title:
                return title
    return None


def _extract_abstract(data: dict[str, Any]) -> str | None:
    collecting = False
    parts: list[str] = []
    for item in data.get("texts", []):
        label = item.get("label")
        text = _clean_text(item.get("text"))
        if label == "section_header":
            if collecting:
                break
            collecting = bool(text and text.casefold() == "abstract")
            continue
        if collecting and text:
            parts.append(text)
    return "\n\n".join(parts) or None


def _extract_doi(nodes: Sequence[BaseNode]) -> str | None:
    for node in nodes[:20]:
        match = DOI_PATTERN.search(node.get_content())
        if match:
            return match.group(0).rstrip(".,;")
    return None


def _page_count(data: dict[str, Any]) -> int | None:
    pages = data.get("pages")
    if isinstance(pages, (dict, list)):
        return len(pages) or None
    return None


def _node_grounding(metadata: dict[str, Any]) -> tuple[
    int | None,
    int | None,
    list[str],
    list[str],
    list[str],
]:
    pages: set[int] = set()
    labels: list[str] = []
    references: list[str] = []
    for item in metadata.get("doc_items", []):
        label = _clean_text(item.get("label"))
        if label and label not in labels:
            labels.append(label)
        reference = _clean_text(item.get("self_ref"))
        if reference:
            references.append(reference)
        for provenance in item.get("prov", []):
            page = provenance.get("page_no")
            if isinstance(page, int) and page >= 1:
                pages.add(page)
    headings = [
        cleaned
        for value in metadata.get("headings", [])
        if (cleaned := _clean_text(value))
    ]
    ordered_pages = sorted(pages)
    return (
        ordered_pages[0] if ordered_pages else None,
        ordered_pages[-1] if ordered_pages else None,
        headings,
        labels,
        references,
    )


def _node_links(metadata: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for value in metadata.get("links", []):
        cleaned = _clean_text(value)
        if cleaned and cleaned not in links:
            links.append(cleaned)
    for item in metadata.get("doc_items", []):
        for key in ("hyperlink", "url", "href"):
            cleaned = _clean_text(item.get(key))
            if cleaned and cleaned not in links:
                links.append(cleaned)
    return links


def canonicalize_docling_output(
    *,
    document_id: UUID,
    llama_documents: Sequence[LlamaDocument],
    llama_nodes: Sequence[BaseNode],
    tokenizer: BaseTokenizer,
    ingestion_version: str,
) -> ParsedDocument:
    """Convert framework objects into the application's stable contracts."""

    if len(llama_documents) != 1:
        raise DocumentIngestionError(
            "Docling returned an unexpected number of documents"
        )
    try:
        docling_data = json.loads(llama_documents[0].get_content())
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DocumentIngestionError(
            "Docling returned an invalid structured document"
        ) from exc

    title = _extract_title(docling_data)
    abstract = _extract_abstract(docling_data)
    doi = _extract_doi(llama_nodes)
    provenance: dict[str, MetadataProvenance] = {}
    if title:
        provenance["title"] = MetadataProvenance.DOCLING
    if abstract:
        provenance["abstract"] = MetadataProvenance.DOCLING
    if doi:
        provenance["doi"] = MetadataProvenance.EXTRACTED

    origin = docling_data.get("origin") or {}
    origin_mime_type = origin.get("mimetype")
    is_presentation = bool(
        isinstance(origin_mime_type, str)
        and "presentationml" in origin_mime_type.casefold()
    )
    parsed_nodes: list[ParsedNode] = []
    for index, llama_node in enumerate(llama_nodes):
        text = llama_node.get_content().strip()
        if not text:
            continue
        metadata = dict(llama_node.metadata)
        page, page_end, headings, labels, references = _node_grounding(metadata)
        has_page_grounding = page is not None
        slide_start = page if is_presentation else None
        slide_end = page_end if is_presentation else None
        if is_presentation:
            page = None
            page_end = None
        captions = [
            cleaned
            for value in metadata.get("captions", [])
            if (cleaned := _clean_text(value))
        ]
        content_kind = "table" if "table" in labels else (labels[0] if labels else "text")
        parsed_nodes.append(
            ParsedNode(
                node_id=stable_node_id(document_id, index, text),
                text=text,
                chunk_index=len(parsed_nodes),
                page=page,
                page_end=page_end,
                section=headings[-1] if headings else None,
                section_path=headings,
                token_count=tokenizer.count_tokens(text),
                metadata={
                    "content_kind": content_kind,
                    "docling_labels": labels,
                    "docling_references": references,
                    "captions": captions,
                    "links": _node_links(metadata),
                    "location_kind": (
                        "slide"
                        if is_presentation
                        else ("page" if has_page_grounding else None)
                    ),
                    "slide_start": slide_start,
                    "slide_end": slide_end,
                },
            )
        )

    canonical_values = {
        "docling_schema": docling_data.get("schema_name"),
        "docling_document_version": docling_data.get("version"),
        "origin_mime_type": origin_mime_type,
        "llama_index_document_id": llama_documents[0].doc_id,
        "llama_index_core_version": _package_version("llama-index-core"),
        "llama_index_reader_version": _package_version(
            "llama-index-readers-docling"
        ),
        "llama_index_node_parser_version": _package_version(
            "llama-index-node-parser-docling"
        ),
    }
    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=title,
            abstract=abstract,
            doi=doi,
            values={
                key: value
                for key, value in canonical_values.items()
                if value is not None
            },
            provenance=provenance,
        ),
        page_count=_page_count(docling_data),
        parser_name="docling",
        parser_version=_package_version("docling"),
        ingestion_version=ingestion_version,
        nodes=parsed_nodes,
    )


class DoclingIngestionAdapter:
    """Use official Docling Reader and Node Parser without vector storage."""

    def __init__(
        self,
        converter: DocumentConverter,
        chunker: HybridChunker,
        tokenizer: BaseTokenizer,
    ) -> None:
        self._converter = converter
        self._chunker = chunker
        self._tokenizer = tokenizer

    def parse(
        self,
        path: Path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        try:
            reader = DoclingReader(
                export_type=DoclingReader.ExportType.JSON,
                doc_converter=self._converter,
                id_func=lambda doc, file_path: str(document_id),
            )
            llama_documents = reader.load_data(
                path,
                extra_info={"document_id": str(document_id)},
            )
            node_parser = DoclingNodeParser(
                chunker=self._chunker,
                id_func=lambda i, node: str(
                    stable_node_id(document_id, i, node.get_content())
                ),
            )
            llama_nodes = node_parser.get_nodes_from_documents(llama_documents)
            return canonicalize_docling_output(
                document_id=document_id,
                llama_documents=llama_documents,
                llama_nodes=llama_nodes,
                tokenizer=self._tokenizer,
                ingestion_version=ingestion_version,
            )
        except DocumentIngestionError:
            raise
        except Exception as exc:
            raise DocumentIngestionError(
                "Docling could not parse the uploaded document"
            ) from exc


@lru_cache(maxsize=4)
def _cached_docling_adapter(
    embedding_model_name: str,
    cache_dir: str | None,
    chunk_max_tokens: int,
    ocr_mode: str,
) -> DoclingIngestionAdapter:
    hf_tokenizer = AutoTokenizer.from_pretrained(
        embedding_model_name,
        cache_dir=cache_dir,
        trust_remote_code=True,
    )
    tokenizer = HuggingFaceTokenizer(
        tokenizer=hf_tokenizer,
        max_tokens=chunk_max_tokens,
    )
    chunker = HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        repeat_table_header=True,
        serializer_provider=MarkdownTableSerializerProvider(),
    )
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = ocr_mode != "disabled"
    if ocr_mode == "force":
        pdf_options.ocr_options.mode = OcrMode.FULL_PAGE
    converter = DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.DOCX,
            InputFormat.PPTX,
            InputFormat.HTML,
            InputFormat.MD,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        },
    )
    return DoclingIngestionAdapter(converter, chunker, tokenizer)


def docling_adapter_for(settings: Settings) -> DoclingIngestionAdapter:
    return _cached_docling_adapter(
        settings.embedding_model_name,
        str(settings.model_cache_dir) if settings.model_cache_dir else None,
        settings.document_chunk_max_tokens,
        settings.docling_ocr_mode,
    )
