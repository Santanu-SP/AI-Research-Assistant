"""Conservative DOI normalization shared by provider and API boundaries."""

import re
from urllib.parse import unquote, urlsplit

from app.core.errors import AppError


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DOI_HOSTS = {"doi.org", "dx.doi.org", "www.doi.org"}


def normalize_doi(value: str) -> str:
    candidate = unquote(value.strip())
    lowered = candidate.casefold()
    if lowered.startswith("doi:"):
        candidate = candidate[4:].strip()
    elif "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in {"http", "https"} or (
            parsed.hostname or ""
        ).casefold() not in DOI_HOSTS:
            raise AppError(
                "A valid DOI or doi.org URL is required",
                status_code=422,
                code="invalid_doi",
            )
        candidate = parsed.path.lstrip("/")

    candidate = candidate.strip().rstrip(".,;").casefold()
    if not DOI_PATTERN.fullmatch(candidate) or any(
        character.isspace() for character in candidate
    ):
        raise AppError(
            "A valid DOI is required",
            status_code=422,
            code="invalid_doi",
        )
    return candidate
