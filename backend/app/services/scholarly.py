"""DOI resolution and deterministic scholarly metadata merging."""

import asyncio
from typing import Any

import httpx

from app.core.config import Settings
from app.domain.documents import MetadataProvenance
from app.domain.scholarly import (
    MetadataConflict,
    ResolutionStatus,
    ScholarlyResolution,
    ScholarlyWorkMetadata,
)
from app.services.doi import normalize_doi
from app.services.scholarly_providers import (
    CrossrefClient,
    OpenAlexClient,
    ProviderError,
)


MERGE_FIELDS = (
    "doi",
    "title",
    "authors",
    "abstract",
    "publication_year",
    "published_at",
    "journal",
    "publisher",
    "openalex_id",
    "crossref_id",
    "landing_url",
    "open_access_status",
)


def _comparable(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, list):
        return [_comparable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def merge_scholarly_metadata(
    crossref: ScholarlyWorkMetadata | None,
    openalex: ScholarlyWorkMetadata | None,
) -> ScholarlyWorkMetadata:
    """Prefer Crossref-deposited bibliographic values, then OpenAlex gaps.

    OpenAlex remains authoritative for its own identifier and OA status. Every
    selected field retains its provider, and disagreements remain auditable.
    """

    if crossref is None and openalex is None:
        return ScholarlyWorkMetadata()
    selected: dict[str, Any] = {}
    provenance: dict[str, MetadataProvenance] = {}
    conflicts: list[MetadataConflict] = []
    for field in MERGE_FIELDS:
        crossref_value = getattr(crossref, field) if crossref else None
        openalex_value = getattr(openalex, field) if openalex else None
        if (
            crossref_value is not None
            and openalex_value is not None
            and _comparable(crossref_value) != _comparable(openalex_value)
        ):
            conflicts.append(
                MetadataConflict(
                    field=field,
                    values={
                        "crossref": crossref_value,
                        "openalex": openalex_value,
                    },
                )
            )

        if field in {"openalex_id", "open_access_status"}:
            chosen = openalex_value if openalex_value is not None else crossref_value
            source = (
                MetadataProvenance.OPENALEX
                if openalex_value is not None
                else MetadataProvenance.CROSSREF
            )
        else:
            chosen = crossref_value if crossref_value is not None else openalex_value
            source = (
                MetadataProvenance.CROSSREF
                if crossref_value is not None
                else MetadataProvenance.OPENALEX
            )
        selected[field] = chosen
        if chosen is not None:
            provenance[field] = source

    provider_metadata: dict[str, Any] = {}
    if crossref:
        provider_metadata.update(crossref.provider_metadata)
    if openalex:
        provider_metadata.update(openalex.provider_metadata)
    return ScholarlyWorkMetadata(
        **selected,
        provider_metadata=provider_metadata,
        field_provenance=provenance,
        conflicts=conflicts,
    )


def provider_clients(
    settings: Settings,
    client: httpx.AsyncClient,
) -> tuple[CrossrefClient, OpenAlexClient]:
    return (
        CrossrefClient(
            client,
            base_url=settings.crossref_base_url,
            mailto=settings.crossref_mailto,
            user_agent=settings.crossref_user_agent,
            timeout=settings.crossref_timeout,
            max_retries=settings.provider_max_retries,
        ),
        OpenAlexClient(
            client,
            base_url=settings.openalex_base_url,
            api_key=settings.openalex_api_key,
            timeout=settings.openalex_timeout,
            max_retries=settings.provider_max_retries,
        ),
    )


class DoiResolver:
    def __init__(self, crossref: CrossrefClient, openalex: OpenAlexClient) -> None:
        self.crossref = crossref
        self.openalex = openalex

    async def resolve(self, doi: str) -> ScholarlyResolution:
        normalized = normalize_doi(doi)
        results = await asyncio.gather(
            self.crossref.lookup_doi(normalized),
            self.openalex.lookup_doi(normalized),
            return_exceptions=True,
        )
        provider_names = (
            MetadataProvenance.CROSSREF,
            MetadataProvenance.OPENALEX,
        )
        resolved: dict[MetadataProvenance, ScholarlyWorkMetadata] = {}
        unavailable: list[MetadataProvenance] = []
        for provider, result in zip(provider_names, results, strict=True):
            if isinstance(result, ProviderError):
                unavailable.append(provider)
            elif isinstance(result, Exception):
                unavailable.append(provider)
            elif result is not None:
                resolved[provider] = result

        if not resolved:
            status = (
                ResolutionStatus.PROVIDER_UNAVAILABLE
                if unavailable
                else ResolutionStatus.UNRESOLVED
            )
            return ScholarlyResolution(
                status=status,
                providers_unavailable=unavailable,
            )

        metadata = merge_scholarly_metadata(
            resolved.get(MetadataProvenance.CROSSREF),
            resolved.get(MetadataProvenance.OPENALEX),
        )
        if metadata.conflicts:
            status = ResolutionStatus.CONFLICTING_METADATA
        elif len(resolved) == 2:
            status = ResolutionStatus.RESOLVED
        else:
            status = ResolutionStatus.PARTIALLY_RESOLVED
        return ScholarlyResolution(
            status=status,
            metadata=metadata,
            providers_resolved=list(resolved),
            providers_unavailable=unavailable,
        )
