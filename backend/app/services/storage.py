from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import hashlib
from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

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
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
    ),
    ".pptx": (
        DocumentType.PPTX,
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }
        ),
    ),
    ".html": (DocumentType.HTML, frozenset({"text/html", "application/xhtml+xml"})),
    ".htm": (DocumentType.HTML, frozenset({"text/html", "application/xhtml+xml"})),
    ".md": (
        DocumentType.MARKDOWN,
        frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
    ),
    ".markdown": (
        DocumentType.MARKDOWN,
        frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
    ),
}
MAX_OFFICE_ARCHIVE_MEMBERS = 10_000
MAX_OFFICE_EXPANDED_BYTES = 250 * 1024 * 1024


class _SafeResearchHtmlParser(HTMLParser):
    """Remove active HTML while retaining research structure for Docling."""

    blocked_containers = {
        "script", "iframe", "object", "applet", "form", "button", "svg", "math",
    }
    blocked_void = {"embed", "input", "link", "meta", "base"}
    blocked = blocked_containers | blocked_void
    allowed_attributes = {"href", "title", "colspan", "rowspan", "scope", "lang"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in self.blocked:
            if normalized in self.blocked_containers:
                self._blocked_depth += 1
            return
        if self._blocked_depth:
            return
        safe_attrs: list[str] = []
        for name, value in attrs:
            name = name.casefold()
            if name not in self.allowed_attributes or value is None:
                continue
            if name == "href" and not value.casefold().startswith(
                ("http://", "https://", "mailto:", "#")
            ):
                continue
            safe_attrs.append(f' {name}="{escape(value, quote=True)}"')
        self.parts.append(f"<{normalized}{''.join(safe_attrs)}>")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() in self.blocked or self._blocked_depth:
            return
        self.handle_starttag(tag, attrs)
        self.parts.append(f"</{tag.casefold()}>")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self.blocked_containers:
            self._blocked_depth = max(0, self._blocked_depth - 1)
            return
        if normalized in self.blocked_void:
            return
        if not self._blocked_depth:
            self.parts.append(f"</{normalized}>")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth:
            self.parts.append(escape(data))

    def sanitized(self) -> str:
        return "".join(self.parts)


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
    checksum: str


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
                "Only PDF, DOCX, PPTX, HTML, and Markdown documents are supported",
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

    def path_for(self, stored_name: str) -> Path:
        """Resolve a validated storage key for document processing."""

        return self._path_for(stored_name)

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
        digest = hashlib.sha256()

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
                    digest.update(chunk)
                    output.write(chunk)

            if size == 0:
                raise AppError(
                    "The uploaded document is empty",
                    status_code=400,
                    code="empty_document",
                )

            self._validate_stored_content(destination, extension)
            if extension in {".html", ".htm"}:
                sanitized = self._sanitize_html(destination)
                destination.write_bytes(sanitized)
                size = len(sanitized)
                digest = hashlib.sha256(sanitized)
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

        return StoredUpload(
            stored_name=stored_name,
            size=size,
            checksum=digest.hexdigest(),
        )

    def save_content(self, content: bytes, extension: str) -> StoredUpload:
        """Promote one bounded remote response into validated local storage."""

        if not content:
            raise AppError("The source is empty", status_code=400, code="empty_source")
        if len(content) > self.max_upload_bytes:
            raise AppError(
                "The source exceeds the configured storage limit",
                status_code=413,
                code="source_too_large",
            )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            stored_name = f"{uuid4().hex}{extension}"
            destination = self._path_for(stored_name)
            destination.write_bytes(content)
            self._validate_stored_content(destination, extension)
            if extension in {".html", ".htm"}:
                content = self._sanitize_html(destination)
                destination.write_bytes(content)
        except AppError:
            if "destination" in locals():
                destination.unlink(missing_ok=True)
            raise
        except OSError as exc:
            if "destination" in locals():
                destination.unlink(missing_ok=True)
            raise AppError(
                "The source could not be stored",
                status_code=500,
                code="document_storage_error",
            ) from exc
        return StoredUpload(
            stored_name=stored_name,
            size=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
        )

    def _validate_stored_content(self, path: Path, extension: str) -> None:
        if extension == ".pdf":
            with path.open("rb") as stored_file:
                if b"%PDF-" not in stored_file.read(1024):
                    raise AppError(
                        "The uploaded file is not a valid PDF",
                        status_code=400,
                        code="invalid_pdf_signature",
                    )
            return
        if extension == ".docx":
            self._validate_office_archive(
                path,
                required_part="word/document.xml",
                label="DOCX",
            )
            return
        if extension == ".pptx":
            self._validate_office_archive(
                path,
                required_part="ppt/presentation.xml",
                label="PPTX",
            )
            return
        if extension in {".html", ".htm", ".md", ".markdown"}:
            self._read_utf8_text(path)
            return
        raise AppError(
            "The uploaded document format is unsupported",
            status_code=400,
            code="unsupported_document_type",
        )

    @staticmethod
    def _read_utf8_text(path: Path) -> str:
        try:
            value = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AppError(
                "The uploaded text document must use UTF-8 encoding",
                status_code=400,
                code="invalid_text_document",
            ) from exc
        if "\x00" in value:
            raise AppError(
                "The uploaded text document contains invalid content",
                status_code=400,
                code="invalid_text_document",
            )
        return value

    def _sanitize_html(self, path: Path) -> bytes:
        parser = _SafeResearchHtmlParser()
        try:
            parser.feed(self._read_utf8_text(path))
            parser.close()
        except (ValueError, AssertionError) as exc:
            raise AppError(
                "The uploaded HTML document could not be parsed safely",
                status_code=400,
                code="invalid_html_document",
            ) from exc
        sanitized = parser.sanitized().strip()
        if not sanitized:
            raise AppError(
                "The uploaded HTML document contains no usable content",
                status_code=400,
                code="invalid_html_document",
            )
        return sanitized.encode("utf-8")

    def _validate_office_archive(
        self,
        path: Path,
        *,
        required_part: str,
        label: str,
    ) -> None:
        error_code = f"invalid_{label.casefold()}_archive"
        try:
            with ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if len(entries) > MAX_OFFICE_ARCHIVE_MEMBERS:
                    raise AppError(
                        f"The {label} archive contains too many files",
                        status_code=400,
                        code=error_code,
                    )
                expanded_limit = min(
                    MAX_OFFICE_EXPANDED_BYTES,
                    self.max_upload_bytes * 20,
                )
                if sum(entry.file_size for entry in entries) > expanded_limit:
                    raise AppError(
                        f"The {label} archive expands beyond the safe size limit",
                        status_code=400,
                        code=error_code,
                    )
                for entry in entries:
                    normalized = entry.filename.replace("\\", "/")
                    member = PurePosixPath(normalized)
                    if (
                        member.is_absolute()
                        or ".." in member.parts
                        or entry.flag_bits & 0x1
                    ):
                        raise AppError(
                            f"The {label} archive contains an unsafe entry",
                            status_code=400,
                            code=error_code,
                        )
                if not {"[Content_Types].xml", required_part}.issubset(names):
                    raise AppError(
                        f"The uploaded file is not a valid {label} document",
                        status_code=400,
                        code=error_code,
                    )
                if any(
                    name.lower().endswith("vbaproject.bin") for name in names
                ):
                    raise AppError(
                        "Macro-enabled Office documents are not supported",
                        status_code=400,
                        code="unsafe_office_document",
                    )
        except AppError:
            raise
        except (BadZipFile, OSError, RuntimeError) as exc:
            raise AppError(
                f"The uploaded file is not a valid {label} document",
                status_code=400,
                code=error_code,
            ) from exc

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
