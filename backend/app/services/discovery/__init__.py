"""Controlled Discovery across curated scholarly and trusted web APIs."""

from app.services.discovery.providers import (
    normalize_doi,
    reconstruct_openalex_abstract,
    search_curated_sources,
    strip_jats_xml,
)
from app.services.discovery.service import (
    import_discovered_sources,
    search_and_annotate,
)

__all__ = [
    "import_discovered_sources",
    "normalize_doi",
    "reconstruct_openalex_abstract",
    "search_and_annotate",
    "search_curated_sources",
    "strip_jats_xml",
]
