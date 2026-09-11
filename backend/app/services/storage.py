from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import Request, UploadFile

from app.core.errors import AppError
from app.domain.documents import DocumentType

UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_ORIGINAL_FILENAME_LENGTH = 255

SUPPORTED_DOCUMENT_TYPES: dict[str, tuple[DocumentType, frozenset[str]]] = {
    ".pdf": (DocumentType.PDF, frozenset({"application/pdf"})),
    ".docx": (
        DocumentType.DOCX,
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
        ),
    ),
    ".txt": (DocumentType.TXT, frozenset({"text/plain"})),
}


@dataclass(frozen=True)
class ValidatedUpload:
    original_name: str
    extension: str
    file_type: DocumentType
    mime_type: str


@dataclass(frozen=True)
class StoredUpload:
    stored_name: str
    size: int


class LocalDocumentStorage:
    def __init__(self, upload_dir: Path, max_upload_bytes: int) -> None:
        self.root = upload_dir.expanduser().resolve()
        self.max_upload_bytes = max_upload_bytes

    def validate(self, upload: UploadFile) -> ValidatedUpload:
        filename = (upload.filename or "").strip()
        if (
            not filename
            or filename in {".", ".."}
            or len(filename) > MAX_ORIGINAL_FILENAME_LENGTH
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            raise AppError(
                "A valid document filename is required",
                status_code=400,
                code="invalid_document_filename",
            )

        extension = Path(filename).suffix.lower()
        supported = SUPPORTED_DOCUMENT_TYPES.get(extension)
        if supported is None:
            raise AppError(
                "Supported document types are PDF, DOCX, and TXT",
                status_code=400,
                code="unsupported_document_type",
            )

        file_type, allowed_mime_types = supported
        mime_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if mime_type not in allowed_mime_types:
            raise AppError(
                "The uploaded file type does not match its filename extension",
                status_code=400,
                code="document_type_mismatch",
            )

        return ValidatedUpload(
            original_name=filename,
            extension=extension,
            file_type=file_type,
            mime_type=mime_type,
        )

    def _path_for(self, stored_name: str) -> Path:
        if (
            not stored_name
            or Path(stored_name).is_absolute()
            or Path(stored_name).name != stored_name
            or "/" in stored_name
            or "\\" in stored_name
        ):
            raise AppError(
                "The stored document reference is invalid",
                status_code=500,
                code="invalid_document_storage_key",
            )

        candidate = (self.root / stored_name).resolve()
        if candidate.parent != self.root:
            raise AppError(
                "The stored document reference is invalid",
                status_code=500,
                code="invalid_document_storage_key",
            )
        return candidate

    async def save(self, upload: UploadFile, extension: str) -> StoredUpload:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppError(
                "Document storage is unavailable",
                status_code=500,
                code="document_storage_error",
            ) from exc

        stored_name = f"{uuid4().hex}{extension}"
        destination = self._path_for(stored_name)
        size = 0

        try:
            with destination.open("xb") as output:
                while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise AppError(
                            "The uploaded document exceeds the configured size limit",
                            status_code=413,
                            code="document_too_large",
                        )
                    output.write(chunk)

            if size == 0:
                raise AppError(
                    "The uploaded document is empty",
                    status_code=400,
                    code="empty_document",
                )
        except AppError:
            destination.unlink(missing_ok=True)
            raise
        except (OSError, RuntimeError) as exc:
            destination.unlink(missing_ok=True)
            raise AppError(
                "The document could not be stored",
                status_code=500,
                code="document_storage_error",
            ) from exc

        return StoredUpload(stored_name=stored_name, size=size)

    def delete(self, stored_name: str) -> bool:
        path = self._path_for(stored_name)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise AppError(
                "The stored document could not be removed",
                status_code=500,
                code="document_storage_error",
            ) from exc
        return True


def get_document_storage(request: Request) -> LocalDocumentStorage:
    settings = request.app.state.settings
    return LocalDocumentStorage(
        settings.document_upload_dir,
        settings.document_max_upload_bytes,
    )
