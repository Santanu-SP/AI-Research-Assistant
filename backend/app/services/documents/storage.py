from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import Request, UploadFile
import httpx

from app.core.errors import AppError
from app.domain.documents import DocumentType, SourceType

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
    ".xlsx": (
        DocumentType.XLSX,
        frozenset(
            {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        ),
    ),
    ".html": (
        DocumentType.HTML,
        frozenset({"text/html", "application/xhtml+xml"}),
    ),
    ".htm": (
        DocumentType.HTML,
        frozenset({"text/html", "application/xhtml+xml"}),
    ),
    ".mp3": (
        DocumentType.AUDIO,
        frozenset({"audio/mpeg", "audio/mp3"}),
    ),
    ".wav": (
        DocumentType.AUDIO,
        frozenset({"audio/wav", "audio/x-wav", "audio/wave"}),
    ),
    ".m4a": (
        DocumentType.AUDIO,
        frozenset({"audio/mp4", "audio/x-m4a", "audio/m4a"}),
    ),
    ".ogg": (
        DocumentType.AUDIO,
        frozenset({"audio/ogg", "application/ogg"}),
    ),
    ".flac": (
        DocumentType.AUDIO,
        frozenset({"audio/flac", "audio/x-flac"}),
    ),
    ".mp4": (
        DocumentType.VIDEO,
        frozenset({"video/mp4"}),
    ),
    ".mov": (
        DocumentType.VIDEO,
        frozenset({"video/quicktime"}),
    ),
    ".mkv": (
        DocumentType.VIDEO,
        frozenset({"video/x-matroska"}),
    ),
    ".webm": (
        DocumentType.VIDEO,
        frozenset({"video/webm", "audio/webm"}),
    ),
    ".png": (
        DocumentType.IMAGE,
        frozenset({"image/png"}),
    ),
    ".jpg": (
        DocumentType.IMAGE,
        frozenset({"image/jpeg"}),
    ),
    ".jpeg": (
        DocumentType.IMAGE,
        frozenset({"image/jpeg"}),
    ),
    ".webp": (
        DocumentType.IMAGE,
        frozenset({"image/webp"}),
    ),
    ".tiff": (
        DocumentType.IMAGE,
        frozenset({"image/tiff"}),
    ),
    ".tif": (
        DocumentType.IMAGE,
        frozenset({"image/tiff"}),
    ),
}

OFFICE_REQUIRED_ENTRIES: dict[str, set[str]] = {
    ".docx": {"[Content_Types].xml", "word/document.xml"},
    ".pptx": {"[Content_Types].xml", "ppt/presentation.xml"},
    ".xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
}

MAX_OFFICE_ARCHIVE_MEMBERS = 10_000
MAX_OFFICE_EXPANDED_BYTES = 250 * 1024 * 1024


def source_type_for_document_type(file_type: DocumentType) -> SourceType:
    if file_type == DocumentType.AUDIO:
        return SourceType.AUDIO_FILE
    if file_type == DocumentType.VIDEO:
        return SourceType.VIDEO_FILE
    if file_type == DocumentType.IMAGE:
        return SourceType.IMAGE_FILE
    if file_type == DocumentType.YOUTUBE:
        return SourceType.YOUTUBE_VIDEO
    if file_type == DocumentType.WEB:
        return SourceType.WEB_PAGE
    return SourceType.UPLOADED_FILE


def _filename_is_safe(filename: str) -> bool:
    if not filename or filename in {".", ".."}:
        return False
    if len(filename) > MAX_ORIGINAL_FILENAME_LENGTH:
        return False
    if "/" in filename or "\\" in filename or "\x00" in filename:
        return False
    return True


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
    storage_backend: str = "local"


class LocalDocumentStorage:
    storage_backend_name: str = "local"

    def __init__(self, upload_dir: Path, max_upload_bytes: int) -> None:
        self.root = upload_dir.expanduser().resolve()
        self.max_upload_bytes = max_upload_bytes

    def validate(self, upload: UploadFile) -> ValidatedUpload:
        filename = (upload.filename or "").strip()
        if not _filename_is_safe(filename):
            raise AppError(
                "A valid document filename is required",
                status_code=400,
                code="invalid_document_filename",
            )

        extension = Path(filename).suffix.lower()
        supported = SUPPORTED_DOCUMENT_TYPES.get(extension)
        if supported is None:
            raise AppError(
                "Unsupported document or media file format",
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

    def get_signed_download_url(
        self,
        stored_name: str,
        *,
        filename: str | None = None,
        expires_in: int = 900,
    ) -> str | None:
        del stored_name, filename, expires_in
        return None

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
            storage_backend=self.storage_backend_name,
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
        if extension in OFFICE_REQUIRED_ENTRIES:
            self._validate_office_archive(path, extension)
            return
        if extension in {".html", ".htm"}:
            with path.open("rb") as stored_file:
                sample = stored_file.read(2048)
                if b"\x00" in sample:
                    raise AppError(
                        "The uploaded file is not valid HTML",
                        status_code=400,
                        code="invalid_html_content",
                    )
            return
        if extension in {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}:
            self._validate_image_signature(path, extension)
            return
        if extension in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".webm"}:
            return
        raise AppError(
            "The uploaded document format is unsupported",
            status_code=400,
            code="unsupported_document_type",
        )

    def _validate_image_signature(self, path: Path, extension: str) -> None:
        with path.open("rb") as stored_file:
            header = stored_file.read(16)
        valid = False
        if extension == ".png":
            valid = header.startswith(b"\x89PNG\r\n\x1a\n")
        elif extension in {".jpg", ".jpeg"}:
            valid = header.startswith(b"\xff\xd8\xff")
        elif extension == ".webp":
            valid = header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        elif extension in {".tiff", ".tif"}:
            valid = header.startswith((b"II*\x00", b"MM\x00*"))
        if not valid:
            raise AppError(
                "The uploaded file is not a valid image",
                status_code=400,
                code="invalid_image_signature",
            )

    def _validate_docx_archive(self, path: Path) -> None:
        self._validate_office_archive(path, ".docx")

    def _validate_office_archive(self, path: Path, extension: str = ".docx") -> None:
        label = extension.lstrip(".").upper()
        code = "invalid_docx_archive" if extension == ".docx" else f"invalid_{extension.lstrip('.')}_archive"
        required_entries = OFFICE_REQUIRED_ENTRIES[extension]
        try:
            with ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if len(entries) > MAX_OFFICE_ARCHIVE_MEMBERS:
                    raise AppError(
                        f"The {label} archive contains too many files",
                        status_code=400,
                        code=code,
                    )
                expanded_limit = min(
                    MAX_OFFICE_EXPANDED_BYTES,
                    self.max_upload_bytes * 20,
                )
                if sum(entry.file_size for entry in entries) > expanded_limit:
                    raise AppError(
                        f"The {label} archive expands beyond the safe size limit",
                        status_code=400,
                        code=code,
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
                            code=code,
                        )
                if not required_entries.issubset(names):
                    raise AppError(
                        f"The uploaded file is not a valid {label} document",
                        status_code=400,
                        code=code,
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
                code=code,
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

    def generate_presigned_url(
        self,
        stored_name: str,
        *,
        method: str = "GET",
        expires_in: int | None = None,
        filename: str | None = None,
        now: datetime | None = None,
    ) -> str | None:
        return None



def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str = "s3") -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


class R2DocumentStorage(LocalDocumentStorage):
    """Cloudflare R2 (S3-compatible) object storage with local staging and signed URLs."""

    storage_backend_name: str = "r2"

    def __init__(
        self,
        upload_dir: Path,
        max_upload_bytes: int,
        *,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str,
        region: str = "auto",
        signed_url_ttl_seconds: int = 900,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(upload_dir, max_upload_bytes)
        if not bucket_name or not access_key_id or not secret_access_key or not endpoint_url:
            raise AppError(
                "Cloudflare R2 credentials and bucket configuration are required",
                status_code=500,
                code="r2_configuration_invalid",
            )
        self.bucket_name = bucket_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url.rstrip("/")
        self.region = region or "auto"
        self.signed_url_ttl_seconds = signed_url_ttl_seconds
        self._client = http_client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))

    def _object_url(self, stored_name: str) -> str:
        safe_key = quote(stored_name, safe="")
        return f"{self.endpoint_url}/{quote(self.bucket_name, safe='')}/{safe_key}"

    def _signed_headers(
        self,
        method: str,
        stored_name: str,
        payload_hash: str,
        content_type: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        amz_date = current.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = current.strftime("%Y%m%d")
        parsed = urlparse(self._object_url(stored_name))
        host = parsed.netloc
        canonical_uri = parsed.path

        headers_to_sign = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers_to_sign["content-type"] = content_type

        sorted_keys = sorted(headers_to_sign.keys())
        canonical_headers = "".join(f"{k}:{headers_to_sign[k].strip()}\n" for k in sorted_keys)
        signed_headers = ";".join(sorted_keys)
        canonical_request = "\n".join(
            [
                method.upper(),
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        sig_key = _signing_key(self.secret_access_key, date_stamp, self.region, "s3")
        signature = hmac.new(sig_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        result = {
            "Authorization": authorization,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if content_type:
            result["Content-Type"] = content_type
        return result

    def generate_presigned_url(
        self,
        stored_name: str,
        *,
        method: str = "GET",
        expires_in: int | None = None,
        filename: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """Generate an S3 SigV4 presigned URL for secure direct file access."""
        self._path_for(stored_name)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        amz_date = current.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = current.strftime("%Y%m%d")
        ttl = expires_in or self.signed_url_ttl_seconds
        parsed = urlparse(self._object_url(stored_name))
        host = parsed.netloc
        canonical_uri = parsed.path
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"

        query_params: dict[str, str] = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(ttl),
            "X-Amz-SignedHeaders": "host",
        }
        if filename:
            safe_filename = filename.replace('"', "")
            query_params["response-content-disposition"] = f'attachment; filename="{safe_filename}"'

        canonical_querystring = urlencode(sorted(query_params.items()), quote_via=quote)
        canonical_request = "\n".join(
            [
                method.upper(),
                canonical_uri,
                canonical_querystring,
                f"host:{host}\n",
                "host",
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        sig_key = _signing_key(self.secret_access_key, date_stamp, self.region, "s3")
        signature = hmac.new(sig_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{parsed.scheme}://{host}{canonical_uri}?{canonical_querystring}&X-Amz-Signature={signature}"

    def get_signed_download_url(
        self,
        stored_name: str,
        *,
        filename: str | None = None,
        expires_in: int = 900,
    ) -> str | None:
        return self.generate_presigned_url(
            stored_name,
            method="GET",
            expires_in=expires_in,
            filename=filename,
        )

    async def save(self, upload: UploadFile, extension: str) -> StoredUpload:
        local_stored = await super().save(upload, extension)
        local_path = self._path_for(local_stored.stored_name)
        content_type = (upload.content_type or "application/octet-stream").split(";", 1)[0].strip()
        try:
            payload = local_path.read_bytes()
            headers = self._signed_headers(
                "PUT",
                local_stored.stored_name,
                local_stored.checksum,
                content_type=content_type,
            )
            response = self._client.put(
                self._object_url(local_stored.stored_name),
                content=payload,
                headers=headers,
            )
            if response.status_code not in {200, 201, 204}:
                raise AppError(
                    "The document could not be uploaded to Cloudflare R2",
                    status_code=502,
                    code="r2_upload_failed",
                )
        except AppError:
            local_path.unlink(missing_ok=True)
            raise
        except httpx.HTTPError as exc:
            local_path.unlink(missing_ok=True)
            raise AppError(
                "Cloudflare R2 storage is unreachable",
                status_code=502,
                code="r2_unavailable",
            ) from exc

        return StoredUpload(
            stored_name=local_stored.stored_name,
            size=local_stored.size,
            checksum=local_stored.checksum,
            storage_backend=self.storage_backend_name,
        )

    def path_for(self, stored_name: str) -> Path:
        """Return local cached path, downloading from R2 if not present on this worker."""
        local_path = self._path_for(stored_name)
        if local_path.is_file():
            return local_path
        payload_hash = hashlib.sha256(b"").hexdigest()
        headers = self._signed_headers("GET", stored_name, payload_hash)
        try:
            response = self._client.get(self._object_url(stored_name), headers=headers)
            if response.status_code == 404:
                return local_path
            response.raise_for_status()
            self.root.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(response.content)
        except httpx.HTTPError as exc:
            raise AppError(
                "Failed to fetch document from Cloudflare R2",
                status_code=502,
                code="r2_download_failed",
            ) from exc
        return local_path

    def delete(self, stored_name: str) -> bool:
        local_deleted = super().delete(stored_name)
        payload_hash = hashlib.sha256(b"").hexdigest()
        headers = self._signed_headers("DELETE", stored_name, payload_hash)
        try:
            response = self._client.delete(self._object_url(stored_name), headers=headers)
            r2_deleted = response.status_code in {200, 202, 204, 404}
        except httpx.HTTPError as exc:
            raise AppError(
                "The stored document could not be removed from Cloudflare R2",
                status_code=502,
                code="r2_delete_failed",
            ) from exc
        return local_deleted or r2_deleted


DocumentStorageBackend = LocalDocumentStorage


def storage_for_settings(settings) -> LocalDocumentStorage:
    if getattr(settings, "storage_backend", "local") == "r2":
        endpoint = settings.r2_endpoint_url
        if not endpoint and settings.r2_account_id:
            endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        return R2DocumentStorage(
            settings.document_upload_dir,
            settings.document_max_upload_bytes,
            bucket_name=settings.r2_bucket_name or "",
            access_key_id=settings.r2_access_key_id or "",
            secret_access_key=settings.r2_secret_access_key or "",
            endpoint_url=endpoint or "",
            region=settings.r2_region,
            signed_url_ttl_seconds=settings.r2_signed_url_ttl_seconds,
        )
    return LocalDocumentStorage(
        settings.document_upload_dir,
        settings.document_max_upload_bytes,
    )


def get_document_storage(request: Request) -> LocalDocumentStorage:
    settings = request.app.state.settings
    return storage_for_settings(settings)
