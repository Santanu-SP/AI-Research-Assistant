from pathlib import Path
from uuid import uuid4

from app.services.pdf_extraction import ExtractedPage, extract_pdf
from app.services.text_processing import chunk_pages, normalize_text
from tests.test_documents_api import make_pdf


def test_pdf_extraction_preserves_pages_and_real_metadata(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(
        make_pdf(
            "First page DOI 10.5555/test.9",
            "Second page text",
            title="Measured Results",
            author="Grace Scientist",
        )
    )
    extracted = extract_pdf(path)

    assert extracted.page_count == 2
    assert [(page.page, page.text.strip()) for page in extracted.pages] == [
        (1, "First page DOI 10.5555/test.9"),
        (2, "Second page text"),
    ]
    assert extracted.title == "Measured Results"
    assert extracted.authors == ["Grace Scientist"]
    assert extracted.doi == "10.5555/test.9"


def test_normalization_is_conservative_for_scientific_text() -> None:
    raw = "RESULTS\n\nThe transfor-\nmer has p < 0.05.\n\n\nEq. E = mc² [12]."
    normalized = normalize_text(raw)

    assert "transformer" in normalized
    assert "p < 0.05" in normalized
    assert "E = mc² [12]" in normalized
    assert "\n\n\n" not in normalized


def test_chunking_retains_page_section_document_and_overlap() -> None:
    document_id = uuid4()
    pages = [
        ExtractedPage(page=1, text="1 INTRODUCTION\n" + "alpha " * 80),
        ExtractedPage(page=2, text="2 METHODS\n" + "beta " * 80),
    ]
    chunks = chunk_pages(document_id, pages, chunk_size=120, overlap=20)

    assert len(chunks) > 2
    assert {chunk.page for chunk in chunks} == {1, 2}
    assert all(chunk.document_id == document_id for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert next(chunk for chunk in chunks if chunk.page == 1).section == "1 INTRODUCTION"
    assert next(chunk for chunk in chunks if chunk.page == 2).section == "2 METHODS"
    assert len({chunk.id for chunk in chunks}) == len(chunks)
