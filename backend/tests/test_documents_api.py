import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services.storage import LocalDocumentStorage

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_MIME = "text/plain"


def upload_document(
    client: TestClient,
    *,
    filename: str = "paper.pdf",
    content: bytes = b"%PDF-1.7\nexample",
    mime_type: str = PDF_MIME,
):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, mime_type)},
    )


def test_upload_valid_pdf_and_return_metadata(
    client: TestClient,
    upload_dir: Path,
) -> None:
    content = b"%PDF-1.7\nresearch"

    response = upload_document(
        client,
        filename="Attention Is All You Need.pdf",
        content=content,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Attention Is All You Need.pdf"
    assert body["type"] == "pdf"
    assert body["mimeType"] == PDF_MIME
    assert body["size"] == len(content)
    assert body["status"] == "ready"
    assert body["createdAt"].endswith("Z")
    assert body["updatedAt"].endswith("Z")
    assert "storedName" not in body
    assert "storagePath" not in body
    assert "storageKey" not in body

    stored_files = list(upload_dir.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == content


def test_upload_valid_docx(client: TestClient) -> None:
    response = upload_document(
        client,
        filename="notes.docx",
        content=b"PK\x03\x04document",
        mime_type=DOCX_MIME,
    )

    assert response.status_code == 201
    assert response.json()["type"] == "docx"
    assert response.json()["mimeType"] == DOCX_MIME


def test_upload_valid_txt(client: TestClient) -> None:
    response = upload_document(
        client,
        filename="notes.txt",
        content=b"plain research notes",
        mime_type=TXT_MIME,
    )

    assert response.status_code == 201
    assert response.json()["type"] == "txt"


def test_stored_filename_is_generated_and_safe(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(client, filename="My Paper.pdf")
    assert response.status_code == 201

    stored_file = next(upload_dir.iterdir())
    assert stored_file.parent == upload_dir
    assert stored_file.name != "My Paper.pdf"
    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", stored_file.name)


def test_duplicate_original_filenames_do_not_collide(
    client: TestClient,
    upload_dir: Path,
) -> None:
    first = upload_document(client, filename="duplicate.pdf", content=b"first")
    second = upload_document(client, filename="duplicate.pdf", content=b"second")

    assert first.status_code == 201
    assert second.status_code == 201
    stored_files = list(upload_dir.iterdir())
    assert len(stored_files) == 2
    assert len({path.name for path in stored_files}) == 2
    assert {path.read_bytes() for path in stored_files} == {b"first", b"second"}


def test_unsupported_extension_is_rejected(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(
        client,
        filename="notes.md",
        content=b"markdown",
        mime_type="text/markdown",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_document_type"
    assert not upload_dir.exists()


def test_mismatched_mime_type_is_rejected(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(
        client,
        filename="paper.pdf",
        content=b"not accepted by metadata",
        mime_type=TXT_MIME,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "document_type_mismatch"
    assert not upload_dir.exists()


def test_oversized_file_is_rejected_and_partial_file_removed(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(client, content=b"x" * 65)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == []


def test_empty_file_is_rejected_and_removed(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(client, content=b"")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_document"
    assert list(upload_dir.iterdir()) == []


def test_path_traversal_filename_is_rejected(
    client: TestClient,
    upload_dir: Path,
) -> None:
    response = upload_document(client, filename="../escape.pdf")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_document_filename"
    assert not upload_dir.exists()
    assert not (upload_dir.parent / "escape.pdf").exists()


def test_empty_filename_is_rejected_cleanly(client: TestClient) -> None:
    response = upload_document(client, filename="")

    assert response.status_code == 422


def test_storage_error_does_not_leak_internal_path(
    client: TestClient,
    upload_dir: Path,
) -> None:
    upload_dir.write_text("this path cannot also be a directory")

    response = upload_document(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "document_storage_error"
    assert str(upload_dir) not in response.text


def test_database_failure_removes_stored_file(
    client: TestClient,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit(_: Session) -> None:
        raise SQLAlchemyError("internal database detail")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = upload_document(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "document_persistence_error"
    assert "internal database detail" not in response.text
    assert list(upload_dir.iterdir()) == []


def test_storage_rejects_deletion_outside_configured_directory(
    upload_dir: Path,
) -> None:
    outside_file = upload_dir.parent / "outside.pdf"
    outside_file.write_bytes(b"must remain")
    storage = LocalDocumentStorage(upload_dir, max_upload_bytes=64)

    with pytest.raises(AppError) as error:
        storage.delete("../outside.pdf")

    assert error.value.code == "invalid_document_storage_key"
    assert outside_file.read_bytes() == b"must remain"


def test_list_documents(client: TestClient) -> None:
    created = upload_document(client).json()

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0] == created


def test_search_documents_by_name_case_insensitively(client: TestClient) -> None:
    matching = upload_document(client, filename="Transformer Notes.pdf").json()
    upload_document(client, filename="Market Study.txt", mime_type=TXT_MIME)

    body = client.get(
        "/api/v1/documents",
        params={"search": "TRANSFORMER"},
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == matching["id"]


def test_filter_documents_by_status_and_validate_status(client: TestClient) -> None:
    created = upload_document(client).json()

    ready = client.get("/api/v1/documents", params={"status": "ready"})
    processing = client.get(
        "/api/v1/documents",
        params={"status": "processing"},
    )
    invalid = client.get("/api/v1/documents", params={"status": "unknown"})

    assert [item["id"] for item in ready.json()["items"]] == [created["id"]]
    assert processing.json()["items"] == []
    assert invalid.status_code == 422


def test_filter_documents_by_type_and_validate_type(client: TestClient) -> None:
    pdf = upload_document(client, filename="paper.pdf").json()
    upload_document(client, filename="notes.txt", mime_type=TXT_MIME)

    filtered = client.get("/api/v1/documents", params={"type": "pdf"})
    invalid = client.get("/api/v1/documents", params={"type": "md"})

    assert [item["id"] for item in filtered.json()["items"]] == [pdf["id"]]
    assert invalid.status_code == 422


def test_document_pagination(client: TestClient) -> None:
    for filename in ("first.txt", "second.txt", "third.txt"):
        response = upload_document(client, filename=filename, mime_type=TXT_MIME)
        assert response.status_code == 201

    response = client.get(
        "/api/v1/documents",
        params={"limit": 1, "offset": 1},
    )

    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1


def test_retrieve_one_document(client: TestClient) -> None:
    created = upload_document(client).json()

    response = client.get(f"/api/v1/documents/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_missing_document_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


def test_delete_document_removes_file_and_database_record(
    client: TestClient,
    upload_dir: Path,
) -> None:
    created = upload_document(client).json()
    stored_file = next(upload_dir.iterdir())

    deleted = client.delete(f"/api/v1/documents/{created['id']}")
    retrieved = client.get(f"/api/v1/documents/{created['id']}")
    listed = client.get("/api/v1/documents").json()

    assert deleted.status_code == 204
    assert not stored_file.exists()
    assert retrieved.status_code == 404
    assert listed["total"] == 0


def test_delete_handles_already_missing_stored_file(
    client: TestClient,
    upload_dir: Path,
) -> None:
    created = upload_document(client).json()
    next(upload_dir.iterdir()).unlink()

    response = client.delete(f"/api/v1/documents/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{created['id']}").status_code == 404


def test_delete_missing_document_returns_404(client: TestClient) -> None:
    response = client.delete(f"/api/v1/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"
