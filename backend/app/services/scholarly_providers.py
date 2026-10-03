"""Bounded Crossref and OpenAlex clients with provider-neutral adapters."""

import asyncio
from datetime import UTC, datetime
from html.parser import HTMLParser
import re
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

from app.domain.documents import MetadataProvenance
from app.domain.scholarly import ScholarlyWorkMetadata
from app.services.doi import normalize_doi


class ProviderError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_abstract(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except (AssertionError, ValueError):
        return None
    cleaned = " ".join(" ".join(parser.parts).split())
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned or None


def reconstruct_openalex_abstract(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned.append((position, word))
    if not positioned:
        return None
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned)


def _first_text(value: object) -> str | None:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    if isinstance(value, list):
        for item in value:
            result = _first_text(item)
            if result:
                return result
    return None


def _date_from_parts(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    date_parts = value.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts or not date_parts[0]:
        return None
    parts = date_parts[0]
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], int):
        return None
    try:
        return datetime(
            parts[0],
            parts[1] if len(parts) > 1 and isinstance(parts[1], int) else 1,
            parts[2] if len(parts) > 2 and isinstance(parts[2], int) else 1,
            tzinfo=UTC,
        )
    except ValueError:
        return None


def _provenance(
    provider: MetadataProvenance, values: dict[str, object]
) -> dict[str, MetadataProvenance]:
    return {key: provider for key, value in values.items() if value is not None}


def crossref_metadata(payload: dict[str, Any]) -> ScholarlyWorkMetadata:
    doi = normalize_doi(str(payload.get("DOI", "")))
    authors = []
    for author in payload.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(
            part for part in (_first_text(author.get("given")), _first_text(author.get("family"))) if part
        )
        if name:
            authors.append(name)
    published_at = None
    for key in ("published-print", "published-online", "published", "issued"):
        published_at = _date_from_parts(payload.get(key))
        if published_at:
            break
    values: dict[str, object] = {
        "doi": doi,
        "title": _first_text(payload.get("title")),
        "authors": authors or None,
        "abstract": normalize_abstract(payload.get("abstract")),
        "publication_year": published_at.year if published_at else None,
        "published_at": published_at,
        "journal": _first_text(payload.get("container-title")),
        "publisher": _first_text(payload.get("publisher")),
        "crossref_id": doi,
        "landing_url": _first_text(payload.get("URL")),
    }
    return ScholarlyWorkMetadata(
        **values,
        provider_metadata={
            "crossref": {
                "type": payload.get("type"),
                "subtype": payload.get("subtype"),
                "license": payload.get("license"),
            }
        },
        field_provenance=_provenance(MetadataProvenance.CROSSREF, values),
    )


def _openalex_id(value: object) -> str | None:
    text = _first_text(value)
    if not text:
        return None
    return text.rstrip("/").rsplit("/", 1)[-1]


def openalex_metadata(payload: dict[str, Any]) -> ScholarlyWorkMetadata:
    ids = payload.get("ids") if isinstance(payload.get("ids"), dict) else {}
    raw_doi = payload.get("doi") or ids.get("doi")
    doi = normalize_doi(str(raw_doi)) if raw_doi else None
    authors = []
    for authorship in payload.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if isinstance(author, dict):
            name = _first_text(author.get("display_name"))
            if name:
                authors.append(name)
    published_at = None
    publication_date = _first_text(payload.get("publication_date"))
    if publication_date:
        try:
            published_at = datetime.fromisoformat(publication_date).replace(tzinfo=UTC)
        except ValueError:
            published_at = None
    year = payload.get("publication_year")
    primary = payload.get("primary_location")
    primary = primary if isinstance(primary, dict) else {}
    source = primary.get("source")
    source = source if isinstance(source, dict) else {}
    access = payload.get("open_access")
    access = access if isinstance(access, dict) else {}
    values: dict[str, object] = {
        "doi": doi,
        "title": _first_text(payload.get("display_name") or payload.get("title")),
        "authors": authors or None,
        "abstract": reconstruct_openalex_abstract(payload.get("abstract_inverted_index")),
        "publication_year": year if isinstance(year, int) else None,
        "published_at": published_at,
        "journal": _first_text(source.get("display_name")),
        "publisher": None,
        "openalex_id": _openalex_id(payload.get("id")),
        "landing_url": _first_text(primary.get("landing_page_url") or raw_doi),
        "open_access_status": _first_text(access.get("oa_status")),
    }
    return ScholarlyWorkMetadata(
        **values,
        provider_metadata={
            "openalex": {
                "type": payload.get("type"),
                "is_oa": access.get("is_oa"),
                "oa_url": access.get("oa_url"),
                "best_oa_location": payload.get("best_oa_location"),
            }
        },
        field_provenance=_provenance(MetadataProvenance.OPENALEX, values),
    )


async def _request_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    provider_name: str,
    timeout: float,
    max_retries: int,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any] | None:
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(
                url,
                params=params,
                headers=headers,
                timeout=httpx.Timeout(timeout),
            )
        except httpx.TimeoutException as exc:
            if attempt < max_retries:
                await sleep(min(0.25 * 2**attempt, 1.0))
                continue
            raise ProviderError(
                f"{provider_name} timed out",
                code=f"{provider_name.casefold()}_timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{provider_name} is unavailable",
                code=f"{provider_name.casefold()}_unavailable",
            ) from exc

        if response.status_code == 404:
            return None
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.25 * 2**attempt
                except ValueError:
                    delay = 0.25 * 2**attempt
                await sleep(min(max(delay, 0.0), 2.0))
                continue
            code = (
                f"{provider_name.casefold()}_rate_limited"
                if response.status_code == 429
                else f"{provider_name.casefold()}_unavailable"
            )
            raise ProviderError(f"{provider_name} is unavailable", code=code)
        if response.status_code in {400, 401, 403}:
            raise ProviderError(
                f"{provider_name} rejected the metadata request",
                code=f"{provider_name.casefold()}_request_rejected",
                status_code=502,
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                f"{provider_name} returned an invalid response",
                code=f"{provider_name.casefold()}_invalid_response",
                status_code=502,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"{provider_name} returned an invalid response",
                code=f"{provider_name.casefold()}_invalid_response",
                status_code=502,
            )
        return payload
    raise AssertionError("provider retry loop exhausted")


class CrossrefClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        mailto: str | None,
        user_agent: str,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.mailto = mailto
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries

    async def lookup_doi(self, doi: str) -> ScholarlyWorkMetadata | None:
        normalized = normalize_doi(doi)
        params = {"mailto": self.mailto} if self.mailto else None
        agent = self.user_agent
        if self.mailto and "mailto:" not in agent:
            agent = f"{agent} (mailto:{self.mailto})"
        payload = await _request_json(
            self.client,
            f"{self.base_url}/works/{quote(normalized, safe='')}",
            provider_name="Crossref",
            timeout=self.timeout,
            max_retries=self.max_retries,
            params=params,
            headers={"User-Agent": agent},
        )
        if payload is None:
            return None
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ProviderError(
                "Crossref returned an invalid response",
                code="crossref_invalid_response",
                status_code=502,
            )
        return crossref_metadata(message)


class OpenAlexClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str | None,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    async def lookup_doi(self, doi: str) -> ScholarlyWorkMetadata | None:
        normalized = normalize_doi(doi)
        return await self.lookup_work(f"https://doi.org/{normalized}")

    async def lookup_work(self, identifier: str) -> ScholarlyWorkMetadata | None:
        normalized = identifier.strip()
        if re.fullmatch(r"W\d+", normalized, re.IGNORECASE):
            normalized = normalized.upper()
        elif "openalex.org/" in normalized.casefold():
            normalized = normalized.rstrip("/").rsplit("/", 1)[-1].upper()
            if not re.fullmatch(r"W\d+", normalized):
                raise ProviderError(
                    "A valid OpenAlex work ID is required",
                    code="invalid_openalex_id",
                    status_code=422,
                )
        elif normalized.casefold().startswith(("http://doi.org/", "https://doi.org/")):
            normalized = f"https://doi.org/{normalize_doi(normalized)}"
        else:
            normalized = f"https://doi.org/{normalize_doi(normalized)}"
        params = {
            "select": (
                "id,ids,doi,display_name,authorships,publication_year,"
                "publication_date,abstract_inverted_index,primary_location,"
                "open_access,best_oa_location,type"
            )
        }
        if self.api_key:
            params["api_key"] = self.api_key
        payload = await _request_json(
            self.client,
            f"{self.base_url}/works/{quote(normalized, safe='')}",
            provider_name="OpenAlex",
            timeout=self.timeout,
            max_retries=self.max_retries,
            params=params,
        )
        return openalex_metadata(payload) if payload is not None else None
