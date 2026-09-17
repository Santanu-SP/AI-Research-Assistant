from io import BytesIO
from pathlib import Path
import re
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.services import documents as document_service
from app.domain.documents import DocumentStatus
from app.models.document import Document, DocumentChunk


PDF_MIME = "application/pdf"


def make_pdf(
    *pages: str,
    title: str | None = "Evidence-Based Research",
    author: str | None = "Ada Researcher",
) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output)
    if title:
        pdf.setTitle(title)
    if author:
        pdf.setAuthor(author)
    for page_text in pages or ("1 INTRODUCTION\nA paper with DOI 10.1234/example.42",):
        text = pdf.beginText(72, 760)
        for line in page_text.splitlines():
            text.textLine(line)
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def upload_document(
    client: TestClient,
    *,
    filename: str = "paper.pdf",
    content: bytes | None = None,
    mime_type: str = PDF_MIME,
):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content if content is not None else make_pdf(), mime_type)},
    )


def test_upload_valid_pdf_processes_metadata_and_chunks(
    client: TestClient,
    upload_dir: Path,
    db_session_factory: sessionmaker[Session],
) -> None:
    content = make_pdf(
        "1 INTRODUCTION\nEvidence on page one. DOI: 10.1234/example.42",
        "2 METHODS\nEvidence on page two.",
    )
    response = upload_document(
        client, filename="Attention Is All You Need.pdf", content=content
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Attention Is All You Need.pdf"
    assert body["type"] == "pdf"
    assert body["mimeType"] == PDF_MIME
    assert body["size"] == len(content)
    assert body["status"] == "indexed"
    assert body["title"] == "Evidence-Based Research"
    assert body["authors"] == ["Ada Researcher"]
    assert body["doi"] == "10.1234/example.42"
    assert body["pageCount"] == 2
    assert body["chunkCount"] >= 2
    assert body["processingError"] is None
    assert body["uploadedAt"].endswith("Z")
    assert "storedName" not in body

    stored_files = list(upload_dir.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == content

    with db_session_factory() as session:
        document = session.get(Document, UUID(body["id"]))
        chunks = list(
            session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index)).all()
        )
        assert document is not None
        assert document.status is DocumentStatus.INDEXED
        assert len(chunks) == body["chunkCount"]
        assert {chunk.page for chunk in chunks} == {1, 2}
        assert all(chunk.document_id == document.id for chunk in chunks)
        assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_upload_uses_centralized_status_lifecycle(
    client: TestClient,
    monkeypatch,
) -> None:
    observed: list[DocumentStatus] = []
    original_commit = document_service._commit

    def recording_commit(session: Session, error_message: str) -> None:
        documents = [
            item for item in [*session.new, *session.identity_map.values()]
            if isinstance(item, Document)
        ]
        if documents:
            observed.append(documents[0].status)
        original_commit(session, error_message)

    monkeypatch.setattr(document_service, "_commit", recording_commit)

    response = upload_document(client)

    assert response.status_code == 201
    assert observed == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PROCESSING,
        DocumentStatus.INDEXED,
    ]


def test_upload_rejects_unsupported_file_type(
    client: TestClient, upload_dir: Path
) -> None:
    response = upload_document(
        client, filename="notes.txt", content=b"plain text", mime_type="text/plain"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_document_type"
    assert not upload_dir.exists()


def test_upload_rejects_mismatched_mime_type(client: TestClient) -> None:
    response = upload_document(client, mime_type="text/plain")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "document_type_mismatch"


def test_upload_rejects_empty_file(client: TestClient, upload_dir: Path) -> None:
    response = upload_document(client, content=b"")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_document"
    assert list(upload_dir.iterdir()) == []


def test_upload_rejects_fake_pdf_signature(client: TestClient, upload_dir: Path) -> None:
    response = upload_document(client, content=b"not a pdf")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_pdf_signature"
    assert list(upload_dir.iterdir()) == []


def test_corrupted_pdf_is_retained_with_failed_status(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    response = upload_document(client, content=b"%PDF-1.7\ncorrupted")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_processing_failed"
    failed_items = client.get(
        "/api/v1/documents", params={"status": "failed"}
    ).json()["items"]
    assert len(failed_items) == 1
    assert failed_items[0]["status"] == "failed"
    assert failed_items[0]["chunkCount"] == 0
    assert failed_items[0]["processingError"]
    with db_session_factory() as session:
        document = session.scalar(select(Document))
        assert document is not None
        assert document.status is DocumentStatus.FAILED
        assert document.processing_error
        assert session.scalar(select(func.count()).select_from(DocumentChunk)) == 0


def test_oversized_file_is_rejected_and_partial_file_removed(
    client: TestClient, upload_dir: Path
) -> None:
    response = upload_document(client, content=b"%PDF-" + b"x" * (1024 * 1024))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert list(upload_dir.iterdir()) == []


def test_stored_filename_is_generated_and_safe(
    client: TestClient, upload_dir: Path
) -> None:
    response = upload_document(client, filename="My Paper.pdf")
    assert response.status_code == 201
    stored_file = next(upload_dir.iterdir())
    assert stored_file.name != "My Paper.pdf"
    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", stored_file.name)


def test_list_filter_and_retrieve_documents(client: TestClient) -> None:
    created = upload_document(client, filename="Transformer Notes.pdf").json()
    listed = client.get(
        "/api/v1/documents", params={"search": "TRANSFORMER", "status": "indexed"}
    )
    retrieved = client.get(f"/api/v1/documents/{created['id']}")
    invalid_status = client.get("/api/v1/documents", params={"status": "ready"})

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == created["id"]
    assert retrieved.json() == created
    assert invalid_status.status_code == 422


def test_delete_document_cascades_chunks_and_removes_file(
    client: TestClient,
    upload_dir: Path,
    db_session_factory: sessionmaker[Session],
) -> None:
    created = upload_document(client).json()
    stored_file = next(upload_dir.iterdir())
    deleted = client.delete(f"/api/v1/documents/{created['id']}")

    assert deleted.status_code == 204
    assert not stored_file.exists()
    assert client.get(f"/api/v1/documents/{created['id']}").status_code == 404
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DocumentChunk)) == 0


def test_missing_document_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/documents/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"
