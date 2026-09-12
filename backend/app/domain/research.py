from enum import StrEnum


class ResearchDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchStatus(StrEnum):
    """Stable summary status exposed by the Research CRUD API."""

    DRAFT = "draft"
    RESEARCHING = "researching"
    COMPLETED = "completed"
    FAILED = "failed"
