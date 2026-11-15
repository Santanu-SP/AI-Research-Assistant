"""Docling skips OCR for PDFs that already have a text layer."""

from io import BytesIO
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas

from app.services.ingestion.pdf import pdf_has_text_layer


def _text_pdf(path: Path) -> Path:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for number in range(3):
        pdf.drawString(72, 760, f"Page {number}: a for loop in Go repeats a block of code many times.")
        pdf.showPage()
    pdf.save()
    path.write_bytes(buffer.getvalue())
    return path


def _scanned_pdf(path: Path) -> Path:
    # A page that is only a picture, like a scan, has no text layer.
    Image.new("RGB", (600, 800), "white").save(path, "PDF")
    return path


def test_text_pdf_is_detected(tmp_path: Path) -> None:
    assert pdf_has_text_layer(_text_pdf(tmp_path / "notes.pdf")) is True


def test_scanned_pdf_keeps_ocr(tmp_path: Path) -> None:
    assert pdf_has_text_layer(_scanned_pdf(tmp_path / "scan.pdf")) is False


def test_unreadable_file_keeps_ocr(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nnot really a pdf")
    assert pdf_has_text_layer(broken) is False


def test_auto_mode_turns_ocr_off_only_for_text_pdfs(tmp_path: Path, monkeypatch) -> None:
    from uuid import uuid4

    from app.core.config import Settings
    from app.services.ingestion import docling

    chosen: list[str] = []

    class _Recorder:
        def parse(self, path, *, document_id, ingestion_version):
            return None

    def fake_adapter(settings, mode):
        chosen.append(mode)
        return _Recorder()

    monkeypatch.setattr(docling, "_adapter_for_mode", fake_adapter)
    settings = Settings(_env_file=None, docling_ocr_mode="auto", worker_enabled=False)
    adapter = docling.docling_adapter_for(settings)
    for path in (_text_pdf(tmp_path / "notes.pdf"), _scanned_pdf(tmp_path / "scan.pdf")):
        adapter.parse(path, document_id=uuid4(), ingestion_version="test")
    assert chosen == ["disabled", "auto"]
