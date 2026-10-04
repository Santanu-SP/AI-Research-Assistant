import os
from pathlib import Path
from uuid import uuid4

from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
import pytest

from app.services.docling_ingestion import (
    DoclingIngestionAdapter,
    MarkdownTableSerializerProvider,
)
from tests.test_documents_api import make_pdf
from tests.test_ingestion import WordTokenizer


pytestmark = [pytest.mark.integration, pytest.mark.docling]


@pytest.mark.skipif(
    os.getenv("RUN_DOCLING_INTEGRATION_TESTS") != "1",
    reason="RUN_DOCLING_INTEGRATION_TESTS is not enabled",
)
def test_official_docling_pdf_pipeline_preserves_page_grounding(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fixture.pdf"
    path.write_bytes(
        make_pdf(
            "Fixture Research\n1 Section One\nTransformer attention evidence.",
            "2 Section Two\nQuantum evidence on page two.",
        )
    )
    options = PdfPipelineOptions()
    options.do_ocr = False
    tokenizer = WordTokenizer()
    adapter = DoclingIngestionAdapter(
        DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            },
        ),
        HybridChunker(
            tokenizer=tokenizer,
            serializer_provider=MarkdownTableSerializerProvider(),
        ),
        tokenizer,
    )

    parsed = adapter.parse(
        path,
        document_id=uuid4(),
        ingestion_version="test-v1",
    )

    assert parsed.page_count == 2
    assert any(node.page == 1 and node.page_end == 2 for node in parsed.nodes)
    assert any("Transformer attention" in node.text for node in parsed.nodes)
    assert any("Quantum evidence" in node.text for node in parsed.nodes)
