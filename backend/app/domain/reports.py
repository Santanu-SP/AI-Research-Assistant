from enum import StrEnum


class SourceType(StrEnum):
    """Controlled evidence classifications exposed by the report API."""

    PEER_REVIEWED = "peer-reviewed"
    OFFICIAL_DOCUMENTATION = "official-documentation"
    INSTITUTIONAL = "institutional"
    TECHNICAL_REPORT = "technical-report"
    PREPRINT = "preprint"
