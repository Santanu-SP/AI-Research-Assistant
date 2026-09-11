from enum import StrEnum


class DocumentType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class DocumentStatus(StrEnum):
    READY = "ready"
    PROCESSING = "processing"
    FAILED = "failed"
