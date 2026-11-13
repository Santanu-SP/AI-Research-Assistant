from enum import StrEnum


class DocumentType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    PPTX = "pptx"
    XLSX = "xlsx"
    HTML = "html"
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    YOUTUBE = "youtube"
    WEB = "web"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class SourceType(StrEnum):
    """Canonical origin categories shared by current and future sources."""

    UPLOADED_FILE = "uploaded_file"
    WEB_PAGE = "web_page"
    YOUTUBE_VIDEO = "youtube_video"
    AUDIO_FILE = "audio_file"
    VIDEO_FILE = "video_file"
    IMAGE_FILE = "image_file"
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
    TRANSCRIPT = "transcript"
    VISUAL_ANALYSIS = "visual_analysis"


class MetadataProvenance(StrEnum):
    """Origin of one canonical metadata value."""

    USER = "user"
    EXTRACTED = "extracted"
    DOCLING = "docling"
    OPENALEX = "openalex"
    CROSSREF = "crossref"
    PUBLISHER = "publisher"
    YOUTUBE = "youtube"
    JINA = "jina"
    WHISPER = "whisper"
    GEMINI_VISION = "gemini_vision"
