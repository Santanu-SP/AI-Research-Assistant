from enum import StrEnum


class DocumentType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class SourceType(StrEnum):
    """Canonical origin categories shared by current and future sources."""

    UPLOADED_FILE = "uploaded_file"
    WEB_PAGE = "web_page"
    DOI = "doi"
    OPENALEX = "openalex"
    CROSSREF = "crossref"


class ContentLevel(StrEnum):
    """What material was actually available to the ingestion pipeline."""

    FULL_TEXT = "full_text"
    ABSTRACT = "abstract"
    METADATA_ONLY = "metadata_only"
    WEB_PAGE = "web_page"
    USER_DOCUMENT = "user_document"


class MetadataProvenance(StrEnum):
    """Origin of one canonical metadata value."""

    USER = "user"
    EXTRACTED = "extracted"
    DOCLING = "docling"
    OPENALEX = "openalex"
    CROSSREF = "crossref"
    PUBLISHER = "publisher"
