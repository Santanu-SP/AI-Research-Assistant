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


class ResearchProgressStage(StrEnum):
    PLANNING = "planning"
    SEARCHING_SOURCES = "searching_sources"
    FINDING_DOCUMENTS = "finding_documents"
    REVIEWING_EVIDENCE = "reviewing_evidence"
    BUILDING_SYNTHESIS = "building_synthesis"


class ResearchProgressStepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
