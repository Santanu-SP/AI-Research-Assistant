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
