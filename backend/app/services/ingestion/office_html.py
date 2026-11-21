"""Document-aware structured ingestion for PPTX, XLSX, and HTML documents."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import UUID

from docx import Document as WordDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
import openpyxl
from pptx import Presentation

from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id
from app.services.ingestion.text import _split_with_overlap, normalize_text
from app.services.ingestion.web import chunk_web_sections, extract_clean_html_sections


def _rows_to_markdown_table(raw_rows: list[list[str]]) -> str | None:
    """Serialize rectangular cell rows into a compact Markdown table."""
    formatted_rows: list[list[str]] = []
    for row in raw_rows:
        cells = [" ".join(str(cell or "").split()).replace("|", "\\|") for cell in row]
        if any(cells):
            formatted_rows.append(cells)
    if not formatted_rows:
        return None
    col_count = max(len(r) for r in formatted_rows)
    padded = [r + [""] * (col_count - len(r)) for r in formatted_rows]
    lines = ["| " + " | ".join(padded[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * max(col_count, 1)) + " |")
    lines.extend("| " + " | ".join(r) + " |" for r in padded[1:])
    return "\n".join(lines)


def _iter_slide_shapes(shapes):
    """Yield every shape on a slide, recursively unfolding grouped shapes."""
    for shape in shapes:
        child_shapes = getattr(shape, "shapes", None)
        if child_shapes is not None:
            yield from _iter_slide_shapes(child_shapes)
        else:
            yield shape


def parse_pptx_document(
    path: Path,
    *,
    document_id: UUID,
    ingestion_version: str,
    chunk_size: int = 2000,
) -> ParsedDocument:
    """Extract slide-aware text, speaker notes, and Markdown tables from a PPTX presentation."""
    try:
        prs = Presentation(str(path))
    except Exception as exc:
        raise DocumentIngestionError(
            "The PPTX presentation could not be parsed",
            code="pptx_processing_failed",
            status_code=422,
        ) from exc

    nodes: list[ParsedNode] = []
    presentation_title: str | None = None

    for slide_idx, slide in enumerate(prs.slides, start=1):
        slide_title: str | None = None
        if slide.shapes.title and slide.shapes.title.text:
            slide_title = " ".join(slide.shapes.title.text.split()).strip() or None
            if presentation_title is None and slide_idx == 1 and slide_title:
                presentation_title = slide_title

        text_blocks: list[str] = []
        figure_refs: list[str] = []
        for shape_idx, shape in enumerate(_iter_slide_shapes(slide.shapes)):
            if getattr(shape, "has_table", False):
                table_md = _rows_to_markdown_table(
                    [[cell.text for cell in row.cells] for row in shape.table.rows]
                )
                if table_md:
                    idx = len(nodes)
                    sec_label = slide_title or f"Slide {slide_idx}"
                    sec_path = [p for p in (presentation_title, sec_label) if p]
                    if len(sec_path) == 2 and sec_path[0] == sec_path[1]:
                        sec_path = [sec_path[0]]
                    nodes.append(
                        ParsedNode(
                            node_id=stable_node_id(document_id, idx, table_md),
                            text=table_md,
                            chunk_index=idx,
                            page=slide_idx,
                            page_end=slide_idx,
                            section=sec_label,
                            section_path=sec_path,
                            token_count=len(table_md.split()),
                            metadata={
                                "content_kind": "table",
                                "slide_number": slide_idx,
                            },
                        )
                    )
            elif getattr(shape, "has_text_frame", False):
                txt = " ".join(shape.text_frame.text.split()).strip()
                if txt and txt != slide_title:
                    text_blocks.append(txt)
            elif shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                figure_refs.append(f"slide-{slide_idx}-picture-{shape_idx}")

        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes_txt = " ".join(slide.notes_slide.notes_text_frame.text.split()).strip()
            if notes_txt:
                text_blocks.append(f"Speaker Notes: {notes_txt}")

        if slide_title or text_blocks:
            combined = "\n\n".join(
                [p for p in ([slide_title] if slide_title else []) + text_blocks if p]
            ).strip()
            if combined:
                start = 0
                while start < len(combined):
                    piece = combined[start : start + chunk_size].strip()
                    if piece:
                        idx = len(nodes)
                        sec_label = slide_title or f"Slide {slide_idx}"
                        sec_path = [p for p in (presentation_title, sec_label) if p]
                        if len(sec_path) == 2 and sec_path[0] == sec_path[1]:
                            sec_path = [sec_path[0]]
                        meta: dict[str, object] = {
                            "content_kind": "slide",
                            "slide_number": slide_idx,
                        }
                        if figure_refs:
                            meta["figure_references"] = figure_refs
                        nodes.append(
                            ParsedNode(
                                node_id=stable_node_id(document_id, idx, piece),
                                text=piece,
                                chunk_index=idx,
                                page=slide_idx,
                                page_end=slide_idx,
                                section=sec_label,
                                section_path=sec_path,
                                token_count=len(piece.split()),
                                metadata=meta,
                            )
                        )
                    start += chunk_size

    if not nodes:
        raise DocumentIngestionError(
            "The presentation contains no retrievable text or tables",
            code="document_processing_failed",
            status_code=422,
        )

    title = presentation_title or path.stem
    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=title,
            values={"slide_count": len(prs.slides)},
            provenance={"title": MetadataProvenance.DOCLING},
        ),
        page_count=len(prs.slides),
        parser_name="docling-pptx",
        parser_version="1.0",
        ingestion_version=f"{ingestion_version}:pptx",
        nodes=nodes,
    )


def parse_xlsx_document(
    path: Path,
    *,
    document_id: UUID,
    ingestion_version: str,
    rows_per_chunk: int = 25,
) -> ParsedDocument:
    """Extract sheet-aware Markdown tables from an XLSX workbook while repeating column headers."""
    try:
        wb = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentIngestionError(
            "The XLSX workbook could not be parsed",
            code="xlsx_processing_failed",
            status_code=422,
        ) from exc

    nodes: list[ParsedNode] = []
    sheet_names = list(wb.sheetnames)
    workbook_title = path.stem

    try:
        for sheet_idx, sheet_name in enumerate(sheet_names, start=1):
            ws = wb[sheet_name]
            non_empty_rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() if cell is not None else "" for cell in row]
                if any(cells):
                    non_empty_rows.append(cells)

            if not non_empty_rows:
                continue

            header = non_empty_rows[0]
            data_rows = non_empty_rows[1:] or [header]
            col_count = max(len(header), 1)
            header_md = "| " + " | ".join(header) + " |"
            sep_md = "| " + " | ".join(["---"] * col_count) + " |"

            for start in range(0, len(data_rows), rows_per_chunk):
                batch = data_rows[start : start + rows_per_chunk]
                body_lines = [
                    "| " + " | ".join(r + [""] * max(0, col_count - len(r))) + " |"
                    for r in batch
                ]
                table_md = "\n".join([header_md, sep_md, *body_lines])
                idx = len(nodes)
                nodes.append(
                    ParsedNode(
                        node_id=stable_node_id(document_id, idx, table_md),
                        text=table_md,
                        chunk_index=idx,
                        page=sheet_idx,
                        page_end=sheet_idx,
                        section=sheet_name,
                        section_path=[workbook_title, sheet_name],
                        token_count=len(table_md.split()),
                        metadata={
                            "content_kind": "table",
                            "sheet_name": sheet_name,
                            "row_start": start + 1,
                            "row_end": start + len(batch),
                        },
                    )
                )
    finally:
        wb.close()

    if not nodes:
        raise DocumentIngestionError(
            "The spreadsheet contains no retrievable data rows",
            code="document_processing_failed",
            status_code=422,
        )

    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=workbook_title,
            values={"sheet_count": len(sheet_names), "sheets": sheet_names},
            provenance={"title": MetadataProvenance.DOCLING},
        ),
        page_count=len(sheet_names),
        parser_name="docling-xlsx",
        parser_version="1.0",
        ingestion_version=f"{ingestion_version}:xlsx",
        nodes=nodes,
    )


def parse_html_document(
    path: Path,
    *,
    document_id: UUID,
    ingestion_version: str,
    chunk_size: int = 1500,
    overlap: int = 150,
) -> ParsedDocument:
    """Extract structured sections and tables from an uploaded HTML file."""
    try:
        raw_html = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise DocumentIngestionError(
            "The HTML document could not be read",
            code="html_processing_failed",
            status_code=422,
        ) from exc

    title, sections = extract_clean_html_sections(raw_html)
    resolved_title = title or path.stem
    nodes = chunk_web_sections(
        document_id,
        sections,
        chunk_size=chunk_size,
        overlap=overlap,
        page_title=resolved_title,
    )
    if not nodes:
        raise DocumentIngestionError(
            "The HTML document contains no retrievable text or tables",
            code="document_processing_failed",
            status_code=422,
        )
    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=resolved_title,
            values={"format": "html"},
            provenance={"title": MetadataProvenance.DOCLING},
        ),
        page_count=1,
        parser_name="docling-html",
        parser_version="1.0",
        ingestion_version=f"{ingestion_version}:html",
        nodes=nodes,
    )


def _heading_level(style_name: str) -> int | None:
    lowered = style_name.strip().lower()
    if not lowered.startswith("heading"):
        return None
    suffix = lowered[len("heading") :].strip()
    if suffix.isdigit():
        return max(1, min(int(suffix), 6))
    return 1


def parse_docx_document(
    path: Path,
    *,
    document_id: UUID,
    ingestion_version: str,
    chunk_size: int = 2000,
    overlap: int = 200,
) -> ParsedDocument:
    """Extract heading-aware sections and Markdown tables from a DOCX file without Docling/Torch."""
    try:
        doc = WordDocument(str(path))
    except Exception as exc:
        raise DocumentIngestionError(
            "The DOCX document could not be parsed",
            code="docx_processing_failed",
            status_code=422,
        ) from exc

    title_prop = " ".join((doc.core_properties.title or "").split()).strip() or None
    author_prop = " ".join((doc.core_properties.author or "").split()).strip() or None
    doc_title: str | None = title_prop
    heading_stack: dict[int, str] = {}
    prose_buffer: list[str] = []
    nodes: list[ParsedNode] = []

    def current_section_info() -> tuple[str | None, list[str]]:
        ordered_headings = [heading_stack[lvl] for lvl in sorted(heading_stack)]
        section = ordered_headings[-1] if ordered_headings else None
        path_items: list[str] = []
        if doc_title:
            path_items.append(doc_title)
        for item in ordered_headings:
            if not path_items or path_items[-1] != item:
                path_items.append(item)
        return section, path_items

    def flush_prose() -> None:
        if not prose_buffer:
            return
        combined = normalize_text("\n\n".join(prose_buffer))
        prose_buffer.clear()
        if not combined:
            return
        section, section_path = current_section_info()
        for piece in _split_with_overlap(combined, chunk_size, overlap):
            idx = len(nodes)
            nodes.append(
                ParsedNode(
                    node_id=stable_node_id(document_id, idx, piece),
                    text=piece,
                    chunk_index=idx,
                    page=None,
                    page_end=None,
                    section=section,
                    section_path=section_path,
                    token_count=len(piece.split()),
                    metadata={"content_kind": "text", "legacy_parser": True},
                )
            )

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text = " ".join((para.text or "").split()).strip()
            if not text:
                continue
            style_name = para.style.name if para.style is not None else ""
            if style_name.strip().lower() == "title":
                if doc_title is None:
                    doc_title = text
                continue
            level = _heading_level(style_name)
            if level is not None:
                flush_prose()
                for deeper in [k for k in heading_stack if k >= level]:
                    del heading_stack[deeper]
                heading_stack[level] = text
                continue
            prose_buffer.append(text)
        elif isinstance(child, CT_Tbl):
            flush_prose()
            table = Table(child, doc)
            table_md = _rows_to_markdown_table(
                [[cell.text for cell in row.cells] for row in table.rows]
            )
            if table_md:
                section, section_path = current_section_info()
                idx = len(nodes)
                nodes.append(
                    ParsedNode(
                        node_id=stable_node_id(document_id, idx, table_md),
                        text=table_md,
                        chunk_index=idx,
                        page=None,
                        page_end=None,
                        section=section,
                        section_path=section_path,
                        token_count=len(table_md.split()),
                        metadata={"content_kind": "table", "legacy_parser": True},
                    )
                )

    flush_prose()

    if not nodes:
        raise DocumentIngestionError(
            "The DOCX document contains no retrievable text or tables",
            code="document_processing_failed",
            status_code=422,
        )

    resolved_title = doc_title or path.stem
    provenance = {"title": MetadataProvenance.EXTRACTED}
    if author_prop:
        provenance["authors"] = MetadataProvenance.EXTRACTED
    try:
        parser_version = version("python-docx")
    except PackageNotFoundError:
        parser_version = None

    return ParsedDocument(
        document_id=document_id,
        metadata=CanonicalMetadata(
            title=resolved_title,
            authors=[author_prop] if author_prop else None,
            values={"format": "docx", "legacy_parser": True},
            provenance=provenance,
        ),
        page_count=None,
        parser_name="python-docx",
        parser_version=parser_version,
        ingestion_version=f"{ingestion_version}:docx",
        nodes=nodes,
    )

