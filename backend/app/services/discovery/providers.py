"""Curated external source connectors for Controlled Discovery (OpenAlex, Crossref, arXiv, Wikipedia)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
import hashlib
import logging
import math
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

import httpx

from app.core.config import Settings
from app.domain.documents import ContentLevel, SourceType
from app.schemas.discovery import (
    DiscoveredSourceCandidate,
    DiscoveryProviderName,
    DiscoveryScope,
    DiscoveryTrustTier,
)

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_CONVERSATIONAL_OPENER_RE = re.compile(
    r"^(?:can you |could you |please )?"
    r"(?:tell me about|tell me|explain to me|explain|what is|what are|"
    r"how does|how do|how is|how are|why does|why do|define|summarize|summarise|"
    r"overview of|describe)\b[:\s]*",
    re.IGNORECASE,
)
_CONVERSATIONAL_TRAILER_RE = re.compile(
    r"\b(?:how (?:it|they) works?|in (?:simple|plain|layman) terms?|"
    r"terms?|in detail|step by step|with examples?)\b[?.!\s]*",
    re.IGNORECASE,
)
_QUERY_STOPWORDS: frozenset[str] = frozenset(
    {
        "about", "all", "also", "an", "and", "are", "as", "at", "background", "be",
        "behind", "between", "by", "can", "cause", "caused", "causes", "causing",
        "could", "current", "currently", "define", "describe", "detail", "details",
        "did", "do", "does", "example", "examples", "explain", "for", "from", "give",
        "going", "happen", "happened", "happening", "happens", "historical",
        "history", "how", "in", "into", "is", "it", "its", "latest", "many", "may",
        "me", "more", "most", "news", "of", "on", "or", "overview", "please",
        "reason", "reasons", "recent", "recently", "role", "show", "simple",
        "start", "started", "step", "summarize", "summarise", "tell", "term",
        "terms", "that", "the", "their", "them", "these", "they", "this", "those",
        "to", "today", "update", "updates", "use", "used", "usage", "using", "was",
        "were", "what", "when", "where", "which", "who", "why", "with", "work",
        "works",
    }
)
_WIKI_QUALIFIERS: frozenset[str] = frozenset(
    {"biological", "chemical", "clinical", "engineering", "general", "medical", "mechanism", "mechanisms", "physical"}
)


def _core_query_tokens(text: str) -> list[str]:
    return [
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _QUERY_STOPWORDS
    ]


def distill_search_query(raw_query: str) -> str:
    """Reduce conversational questions into sharp search terms for academic APIs."""
    cleaned = " ".join(raw_query.split()).strip()
    if not cleaned:
        return ""
    stripped = _CONVERSATIONAL_OPENER_RE.sub("", cleaned)
    stripped = _CONVERSATIONAL_TRAILER_RE.sub(" ", stripped)
    stripped = " ".join(stripped.split()).strip(" ?.,!;:")
    words = _TOKEN_RE.findall(cleaned.lower())
    was_question = len(words) > 5 or stripped.lower() != cleaned.rstrip(" ?.!").lower()
    if was_question:
        core = _core_query_tokens(stripped or cleaned)
        if len(core) >= 2:
            return " ".join(core[:6])
    return stripped or cleaned

TRUSTED_WEB_DOMAINS: frozenset[str] = frozenset(
    {
        "wikipedia.org",
        "en.wikipedia.org",
        "arxiv.org",
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "who.int",
        "nature.com",
        "science.org",
        "acm.org",
        "ieee.org",
        "ietf.org",
        "w3.org",
        "python.org",
        "postgresql.org",
        "developer.mozilla.org",
        "react.dev",
        "fastapi.tiangolo.com",
        "pytorch.org",
        "huggingface.co",
        # Reputable news wires, newspapers, and foreign-policy journals
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "theguardian.com",
        "aljazeera.com",
        "nytimes.com",
        "washingtonpost.com",
        "wsj.com",
        "ft.com",
        "economist.com",
        "bloomberg.com",
        "npr.org",
        "pbs.org",
        "thehindu.com",
        "indianexpress.com",
        "hindustantimes.com",
        "timesofindia.indiatimes.com",
        "cfr.org",
        "chathamhouse.org",
        "foreignaffairs.com",
        "crisisgroup.org",
        "dw.com",
        "france24.com",
        "news.google.com",
    }
)

REPUTABLE_NEWS_SITE_QUERY = (
    "site:reuters.com OR site:apnews.com OR site:bbc.com OR site:theguardian.com "
    "OR site:aljazeera.com OR site:thehindu.com OR site:indianexpress.com "
    "OR site:nytimes.com OR site:cfr.org OR site:foreignaffairs.com "
    "OR site:dw.com OR site:france24.com"
)

_REPUTABLE_NEWS_OUTLETS: tuple[str, ...] = (
    "reuters",
    "associated press",
    "ap news",
    "bbc",
    "the guardian",
    "al jazeera",
    "new york times",
    "washington post",
    "wall street journal",
    "financial times",
    "the economist",
    "bloomberg",
    "npr",
    "pbs",
    "the hindu",
    "indian express",
    "hindustan times",
    "times of india",
    "council on foreign relations",
    "chatham house",
    "foreign affairs",
    "crisis group",
    "deutsche welle",
    "dw",
    "france 24",
)


def is_trusted_domain(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host.endswith((".edu", ".gov", ".ac.uk", ".gov.uk")):
        return True
    return any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_WEB_DOMAINS)


def normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    cleaned = cleaned.rstrip(".").strip()
    return cleaned.lower() or None


def strip_jats_xml(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = unescape(_TAG_RE.sub(" ", raw))
    normalized = " ".join(cleaned.split()).strip()
    return normalized or None


def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and pos >= 0:
                positioned.append((pos, str(word)))
    if not positioned:
        return None
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned).strip() or None


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


_ARXIV_PDF_SUFFIX_RE = re.compile(r"^(https?://(?:export\.)?arxiv\.org/pdf/[^?#]+?)\.pdf$", re.IGNORECASE)


def canonical_arxiv_pdf_url(url: str | None) -> str | None:
    """arXiv answers ``/pdf/<id>.pdf`` with a relative redirect to ``/pdf/<id>``.

    The PDF fetcher refuses relative redirects, so the full text was lost and
    only the abstract was saved. Asking for ``/pdf/<id>`` directly avoids the
    redirect.
    """
    if not url:
        return url
    cleaned = url.strip().replace("http://arxiv.org/", "https://arxiv.org/")
    match = _ARXIV_PDF_SUFFIX_RE.match(cleaned)
    return match.group(1) if match else cleaned


def _candidate_id(provider: str, identifier: str) -> str:
    digest = hashlib.sha256(f"{provider}:{identifier}".encode("utf-8")).hexdigest()[:16]
    return f"{provider}-{digest}"


def _build_headers(mailto: str | None) -> dict[str, str]:
    contact = (
        f"https://github.com/Santanu-SP/AI-Research-Assistant; mailto:{mailto}"
        if mailto
        else "https://github.com/Santanu-SP/AI-Research-Assistant"
    )
    ua = f"AIResearchAssistant/1.0 ({contact})"
    return {"User-Agent": ua, "Accept": "application/json, application/atom+xml, text/xml"}


def _year_from_int(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 9999 else None


def search_openalex(
    query: str,
    *,
    limit: int = 6,
    timeout_seconds: float = 12.0,
    mailto: str | None = None,
    client: httpx.Client | None = None,
) -> list[DiscoveredSourceCandidate]:
    params: dict[str, Any] = {
        "search": query.strip(),
        "per-page": min(max(limit, 1), 15),
        "select": (
            "id,doi,title,publication_year,cited_by_count,type,"
            "open_access,best_oa_location,primary_location,authorships,abstract_inverted_index"
        ),
    }
    if mailto:
        params["mailto"] = mailto
    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=5.0))
    try:
        resp = active.get("https://api.openalex.org/works", params=params, headers=_build_headers(mailto))
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            active.close()

    candidates: list[DiscoveredSourceCandidate] = []
    for work in payload.get("results") or []:
        title = " ".join(str(work.get("title") or "").split()).strip()
        if not title:
            continue
        abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        best_oa = work.get("best_oa_location") or {}
        primary_loc = work.get("primary_location") or {}
        oa_info = work.get("open_access") or {}
        pdf_url = best_oa.get("pdf_url") or oa_info.get("oa_url")
        if pdf_url and not str(pdf_url).lower().endswith(".pdf") and not best_oa.get("pdf_url"):
            # OpenAlex oa_url may be a landing page rather than a direct PDF binary.
            pdf_url = None
        doi = normalize_doi(work.get("doi"))
        raw_id = str(work.get("id") or "").strip()
        openalex_id = raw_id.rsplit("/", 1)[-1] if raw_id else None
        landing_url = (
            primary_loc.get("landing_page_url")
            or best_oa.get("landing_page_url")
            or oa_info.get("oa_url")
            or (f"https://doi.org/{doi}" if doi else None)
            or raw_id
        )
        if not landing_url:
            continue
        if not abstract and not (pdf_url or oa_info.get("is_oa")):
            continue

        source_obj = primary_loc.get("source") or {}
        venue = str(source_obj.get("display_name") or "").strip() or None
        is_preprint = str(work.get("type") or "").lower() == "preprint" or (
            venue is not None and "arxiv" in venue.lower()
        )
        authors: list[str] = []
        for authorship in (work.get("authorships") or [])[:12]:
            author_name = ((authorship or {}).get("author") or {}).get("display_name")
            if author_name:
                authors.append(str(author_name).strip())

        is_oa = bool(oa_info.get("is_oa") or pdf_url)
        trust_tier: DiscoveryTrustTier = "preprint" if is_preprint else "peer-reviewed"
        content_level = (
            ContentLevel.FULL_TEXT
            if pdf_url
            else (ContentLevel.ABSTRACT if abstract else ContentLevel.METADATA_ONLY)
        )
        candidates.append(
            DiscoveredSourceCandidate(
                candidate_id=_candidate_id("openalex", doi or openalex_id or title),
                provider="openalex",
                trust_tier=trust_tier,
                source_type=SourceType.OPENALEX,
                content_level=content_level,
                title=title[:1000],
                authors=authors,
                publication_year=_year_from_int(work.get("publication_year")),
                publisher=venue[:300] if venue else None,
                abstract=abstract[:20_000] if abstract else None,
                doi=doi,
                openalex_id=openalex_id,
                url=str(landing_url)[:2048],
                open_access_pdf_url=(canonical_arxiv_pdf_url(str(pdf_url)) or "")[:2048] if pdf_url else None,
                citation_count=int(work.get("cited_by_count")) if work.get("cited_by_count") is not None else None,
                is_open_access=is_oa,
            )
        )
    return candidates


def search_crossref(
    query: str,
    *,
    limit: int = 6,
    timeout_seconds: float = 12.0,
    mailto: str | None = None,
    client: httpx.Client | None = None,
) -> list[DiscoveredSourceCandidate]:
    params: dict[str, Any] = {
        "query": query.strip(),
        "rows": min(max(limit, 1), 15),
        "select": (
            "DOI,title,author,published-print,published-online,created,"
            "container-title,abstract,is-referenced-by-count,URL,type,link"
        ),
    }
    if mailto:
        params["mailto"] = mailto
    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=5.0))
    try:
        resp = active.get("https://api.crossref.org/works", params=params, headers=_build_headers(mailto))
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            active.close()

    items = ((payload.get("message") or {}).get("items") or [])
    candidates: list[DiscoveredSourceCandidate] = []
    for work in items:
        titles = work.get("title") or []
        title = " ".join(str(titles[0]).split()).strip() if titles else ""
        if not title:
            continue
        doi = normalize_doi(work.get("DOI"))
        abstract = strip_jats_xml(work.get("abstract"))
        url = str(work.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip()
        if not url:
            continue

        pdf_url: str | None = None
        for link in work.get("link") or []:
            if not isinstance(link, dict):
                continue
            ctype = str(link.get("content-type") or "").lower()
            if "pdf" in ctype and link.get("URL"):
                pdf_url = str(link["URL"]).strip()
                break
        if not abstract and not pdf_url:
            continue

        authors: list[str] = []
        for auth in (work.get("author") or [])[:12]:
            given = str(auth.get("given") or "").strip()
            family = str(auth.get("family") or "").strip()
            full = " ".join(part for part in (given, family) if part)
            if full:
                authors.append(full)

        year = None
        for field in ("published-print", "published-online", "created"):
            parts = ((work.get(field) or {}).get("date-parts") or [])
            if parts and isinstance(parts[0], list) and parts[0]:
                year = _year_from_int(parts[0][0])
                if year:
                    break

        containers = work.get("container-title") or []
        venue = " ".join(str(containers[0]).split()).strip() if containers else None
        is_preprint = "posted-content" in str(work.get("type") or "").lower()
        candidates.append(
            DiscoveredSourceCandidate(
                candidate_id=_candidate_id("crossref", doi or url),
                provider="crossref",
                trust_tier="preprint" if is_preprint else "peer-reviewed",
                source_type=SourceType.CROSSREF,
                content_level=ContentLevel.FULL_TEXT if pdf_url else ContentLevel.ABSTRACT,
                title=title[:1000],
                authors=authors,
                publication_year=year,
                publisher=venue[:300] if venue else None,
                abstract=abstract[:20_000] if abstract else None,
                doi=doi,
                crossref_id=doi,
                url=url[:2048],
                open_access_pdf_url=pdf_url[:2048] if pdf_url else None,
                citation_count=(
                    int(work.get("is-referenced-by-count"))
                    if work.get("is-referenced-by-count") is not None
                    else None
                ),
                is_open_access=bool(pdf_url),
            )
        )
    return candidates


def search_arxiv(
    query: str,
    *,
    limit: int = 5,
    timeout_seconds: float = 12.0,
    client: httpx.Client | None = None,
) -> list[DiscoveredSourceCandidate]:
    # arXiv only applies "all:" to the first word of a plain query and ORs the
    # rest, which brings back loosely related papers. Require every key word
    # first, then the first three, and only fall back to the loose query if
    # neither finds anything.
    terms = _core_query_tokens(query)[:6]
    attempts: list[str] = []
    if len(terms) >= 2:
        attempts.append(" AND ".join(f"all:{term}" for term in terms))
    if len(terms) > 3:
        attempts.append(" AND ".join(f"all:{term}" for term in terms[:3]))
    attempts.append(f"all:{query.strip()}")

    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=5.0))

    def _fetch(search_query: str) -> ET.Element:
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max(limit, 1), 10),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        resp = active.get("https://export.arxiv.org/api/query", params=params, headers=_build_headers(None))
        resp.raise_for_status()
        return ET.fromstring(resp.text)

    try:
        for search_query in attempts:
            root = _fetch(search_query)
            if root.findall("atom:entry", _ARXIV_NS):
                break
    finally:
        if own_client:
            active.close()

    candidates: list[DiscoveredSourceCandidate] = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        title_el = entry.find("atom:title", _ARXIV_NS)
        summary_el = entry.find("atom:summary", _ARXIV_NS)
        id_el = entry.find("atom:id", _ARXIV_NS)
        published_el = entry.find("atom:published", _ARXIV_NS)
        title = " ".join((title_el.text or "").split()).strip() if title_el is not None else ""
        abstract = " ".join((summary_el.text or "").split()).strip() if summary_el is not None else ""
        entry_url = (id_el.text or "").strip() if id_el is not None else ""
        if not title or not entry_url:
            continue

        pdf_url: str | None = None
        html_url = entry_url
        for link in entry.findall("atom:link", _ARXIV_NS):
            rel = link.attrib.get("rel", "")
            href = (link.attrib.get("href") or "").strip().replace("http://arxiv.org/", "https://arxiv.org/")
            link_title = link.attrib.get("title", "")
            if rel == "alternate" and href:
                html_url = href
            elif (link_title == "pdf" or "/pdf/" in href) and href:
                pdf_url = canonical_arxiv_pdf_url(href)
        html_url = html_url.replace("http://arxiv.org/", "https://arxiv.org/")
        if not pdf_url and "/abs/" in html_url:
            pdf_url = html_url.replace("/abs/", "/pdf/")

        authors = [
            " ".join((name_el.text or "").split()).strip()
            for author_el in entry.findall("atom:author", _ARXIV_NS)[:12]
            if (name_el := author_el.find("atom:name", _ARXIV_NS)) is not None and (name_el.text or "").strip()
        ]
        doi_el = entry.find("arxiv:doi", _ARXIV_NS)
        doi = normalize_doi(doi_el.text) if doi_el is not None else None
        year = _year_from_int((published_el.text or "")[:4]) if published_el is not None else None

        candidates.append(
            DiscoveredSourceCandidate(
                candidate_id=_candidate_id("arxiv", entry_url),
                provider="arxiv",
                trust_tier="preprint",
                source_type=SourceType.DOI if doi else SourceType.WEB_PAGE,
                content_level=ContentLevel.FULL_TEXT if pdf_url else ContentLevel.ABSTRACT,
                title=title[:1000],
                authors=authors,
                publication_year=year,
                publisher="arXiv",
                abstract=abstract[:20_000] if abstract else None,
                doi=doi,
                url=html_url[:2048],
                open_access_pdf_url=pdf_url[:2048] if pdf_url else None,
                is_open_access=True,
            )
        )
    return candidates


def _parse_news_pubdate(raw_date: str | None) -> tuple[int | None, str | None]:
    if not raw_date:
        return None, None
    try:
        parsed = parsedate_to_datetime(raw_date.strip())
        return _year_from_int(parsed.year), parsed.strftime("%Y-%m-%d")
    except Exception:
        return None, None


def _is_reputable_outlet(publisher: str | None, url: str | None) -> bool:
    pub_lower = (publisher or "").lower()
    if any(outlet in pub_lower for outlet in _REPUTABLE_NEWS_OUTLETS):
        return True
    if url:
        host = urlparse(url).hostname
        if host and is_trusted_domain(host) and not host.endswith("news.google.com"):
            return True
    return False


def _clean_rss_summary(raw_html: str | None, headline: str) -> str:
    text = strip_jats_xml(raw_html) or ""
    # Google News RSS descriptions often repeat "<headline>  <publisher>".
    if text.lower().startswith(headline.lower()):
        text = text[len(headline) :].strip(" -|:\u00a0")
    return " ".join(text.split()).strip()


def _build_news_candidate(
    *,
    clean_title: str,
    publisher: str,
    article_url: str,
    raw_pub_date: str | None,
    raw_summary: str | None,
) -> DiscoveredSourceCandidate:
    year, date_label = _parse_news_pubdate(raw_pub_date)
    summary = _clean_rss_summary(raw_summary, clean_title)
    if summary.lower() == publisher.lower():
        summary = ""
    meta_date = f" ({date_label})" if date_label else ""
    abstract = f"{clean_title}. Reported by {publisher}{meta_date}."
    if summary:
        abstract = f"{abstract} {summary}"
    return DiscoveredSourceCandidate(
        candidate_id=_candidate_id("news", f"{publisher}:{clean_title}"),
        provider="wikipedia",
        trust_tier="institutional",
        source_type=SourceType.WEB_PAGE,
        content_level=ContentLevel.WEB_PAGE,
        title=clean_title[:1000],
        authors=[],
        publication_year=year,
        publisher=publisher[:300],
        abstract=abstract[:20_000],
        url=article_url[:2048],
        is_open_access=True,
    )


def _fetch_google_news_rss(
    query: str,
    *,
    limit: int,
    timeout_seconds: float,
    client: httpx.Client | None,
) -> list[DiscoveredSourceCandidate]:
    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=4.0))
    try:
        resp = active.get(
            "https://news.google.com/rss/search",
            params={
                "q": f"{query.strip()} ({REPUTABLE_NEWS_SITE_QUERY})",
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml, text/xml"},
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
    except Exception:
        return []
    finally:
        if own_client:
            active.close()

    candidates: list[DiscoveredSourceCandidate] = []
    for item in root.findall("./channel/item"):
        raw_title = " ".join((item.findtext("title") or "").split()).strip()
        link = (item.findtext("link") or "").strip()
        if not raw_title or not link.startswith("https://"):
            continue
        source_el = item.find("source")
        publisher = " ".join((source_el.text or "").split()).strip() if source_el is not None else ""
        source_url = (source_el.attrib.get("url") or "").strip() if source_el is not None else ""
        clean_title = raw_title
        if publisher and raw_title.endswith(f" - {publisher}"):
            clean_title = raw_title[: -len(publisher) - 3].strip()
        elif " - " in raw_title and not publisher:
            maybe_title, maybe_pub = raw_title.rsplit(" - ", 1)
            clean_title, publisher = maybe_title.strip(), maybe_pub.strip()
        if not publisher or not _is_reputable_outlet(publisher, source_url):
            continue

        candidates.append(
            _build_news_candidate(
                clean_title=clean_title,
                publisher=publisher,
                article_url=link,
                raw_pub_date=item.findtext("pubDate"),
                raw_summary=item.findtext("description"),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _fetch_bing_news_rss(
    query: str,
    *,
    limit: int,
    timeout_seconds: float,
    client: httpx.Client | None,
) -> list[DiscoveredSourceCandidate]:
    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=4.0))
    try:
        resp = active.get(
            "https://www.bing.com/news/search",
            params={"q": query.strip(), "format": "rss"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml, text/xml"},
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
    except Exception:
        return []
    finally:
        if own_client:
            active.close()

    candidates: list[DiscoveredSourceCandidate] = []
    for item in root.findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split()).strip()
        raw_link = (item.findtext("link") or "").strip()
        if not title or not raw_link:
            continue
        direct_urls = parse_qs(urlparse(raw_link).query).get("url") or []
        article_url = direct_urls[0] if direct_urls else raw_link
        if not article_url.startswith("https://"):
            continue

        publisher = ""
        for child in item:
            if child.tag.endswith("Source") and child.text:
                publisher = " ".join(child.text.split()).strip()
                break
        if not publisher:
            publisher = urlparse(article_url).hostname or ""
        if not _is_reputable_outlet(publisher, article_url):
            continue

        candidates.append(
            _build_news_candidate(
                clean_title=title,
                publisher=publisher,
                article_url=article_url,
                raw_pub_date=item.findtext("pubDate"),
                raw_summary=item.findtext("description"),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def search_reputable_news(
    query: str,
    *,
    limit: int = 4,
    timeout_seconds: float = 8.0,
    client: httpx.Client | None = None,
) -> list[DiscoveredSourceCandidate]:
    """Discover recent reporting from curated reputable news organizations via RSS."""
    bing_items = _fetch_bing_news_rss(
        query,
        limit=max(limit, 4),
        timeout_seconds=timeout_seconds,
        client=client,
    )
    google_items = _fetch_google_news_rss(
        query,
        limit=max(limit, 4),
        timeout_seconds=timeout_seconds,
        client=client,
    )
    merged: dict[str, DiscoveredSourceCandidate] = {}
    for item in [*bing_items, *google_items]:
        key = _title_key(item.title)
        existing = merged.get(key)
        if existing is None or len(item.abstract or "") > len(existing.abstract or ""):
            merged[key] = item
    return list(merged.values())[:limit]


def search_wikipedia(
    query: str,
    *,
    limit: int = 4,
    timeout_seconds: float = 12.0,
    client: httpx.Client | None = None,
) -> list[DiscoveredSourceCandidate]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query.strip(),
        "gsrlimit": min(max(limit, 1), 6),
        "prop": "extracts|info",
        "exintro": 1,
        "explaintext": 1,
        "inprop": "url",
        "format": "json",
    }
    own_client = client is None
    active = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=5.0))
    try:
        resp = active.get("https://en.wikipedia.org/w/api.php", params=params, headers=_build_headers(None))
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            active.close()

    pages = list(((payload.get("query") or {}).get("pages") or {}).values())
    pages.sort(key=lambda page: int(page.get("index", 999)))
    candidates: list[DiscoveredSourceCandidate] = []
    for page in pages:
        title = " ".join(str(page.get("title") or "").split()).strip()
        extract = " ".join(str(page.get("extract") or "").split()).strip()
        fullurl = str(page.get("fullurl") or "").strip()
        if not title or not fullurl or len(extract) < 40:
            continue
        if "may refer to:" in extract[:120].lower():
            continue
        candidates.append(
            DiscoveredSourceCandidate(
                candidate_id=_candidate_id("wikipedia", fullurl),
                provider="wikipedia",
                trust_tier="institutional",
                source_type=SourceType.WEB_PAGE,
                content_level=ContentLevel.WEB_PAGE,
                title=title[:1000],
                authors=[],
                publication_year=None,
                publisher="Wikipedia",
                abstract=extract[:20_000],
                url=fullurl[:2048],
                is_open_access=True,
            )
        )
    return candidates


def _merge_candidates(
    existing: DiscoveredSourceCandidate,
    incoming: DiscoveredSourceCandidate,
) -> DiscoveredSourceCandidate:
    primary, secondary = (
        (existing, incoming)
        if _provider_priority(existing.provider) >= _provider_priority(incoming.provider)
        else (incoming, existing)
    )
    merged_pdf = primary.open_access_pdf_url or secondary.open_access_pdf_url
    merged_abstract = (
        primary.abstract
        if len(primary.abstract or "") >= len(secondary.abstract or "")
        else secondary.abstract
    )
    merged_level = (
        ContentLevel.FULL_TEXT
        if merged_pdf
        else (
            primary.content_level
            if primary.content_level != ContentLevel.METADATA_ONLY
            else secondary.content_level
        )
    )
    return primary.model_copy(
        update={
            "doi": primary.doi or secondary.doi,
            "openalex_id": primary.openalex_id or secondary.openalex_id,
            "crossref_id": primary.crossref_id or secondary.crossref_id,
            "authors": primary.authors or secondary.authors,
            "publication_year": primary.publication_year or secondary.publication_year,
            "publisher": primary.publisher or secondary.publisher,
            "abstract": merged_abstract,
            "open_access_pdf_url": merged_pdf,
            "is_open_access": primary.is_open_access or secondary.is_open_access,
            "citation_count": max(
                [c for c in (primary.citation_count, secondary.citation_count) if c is not None],
                default=None,
            ),
            "content_level": merged_level,
        }
    )


def _provider_priority(provider: DiscoveryProviderName) -> int:
    return {"openalex": 4, "crossref": 3, "arxiv": 2, "wikipedia": 1}.get(provider, 0)


def _score_candidate(
    candidate: DiscoveredSourceCandidate,
    core_terms: set[str],
    subject_terms: set[str],
    subject_phrase: str,
) -> float:
    tier_score = {
        "peer-reviewed": 4.0,
        "preprint": 3.0,
        "official-documentation": 2.5,
        "institutional": 2.0,
    }.get(candidate.trust_tier, 1.0)
    full_text_bonus = (
        2.0
        if candidate.open_access_pdf_url or candidate.content_level == ContentLevel.WEB_PAGE
        else 0.0
    )
    title_lower = candidate.title.lower()
    title_tokens = set(_TOKEN_RE.findall(title_lower))
    abstract_tokens = set(_TOKEN_RE.findall((candidate.abstract or "").lower()))
    all_tokens = title_tokens | abstract_tokens

    active_subject = subject_terms or core_terms
    subject_title_hits = len(active_subject & title_tokens) if active_subject else 0
    subject_any_hits = len(active_subject & all_tokens) if active_subject else 0
    core_any_hits = len(core_terms & all_tokens) if core_terms else 0

    phrase_bonus = 3.0 if subject_phrase and subject_phrase in title_lower else 0.0
    title_overlap = (subject_title_hits / len(active_subject)) * 7.0 if active_subject else 0.0
    core_overlap = (core_any_hits / len(core_terms)) * 6.0 if core_terms else 0.0
    off_topic_penalty = (
        -12.0
        if active_subject and subject_any_hits == 0
        else (-3.0 if len(active_subject) >= 2 and subject_any_hits < len(active_subject) else 0.0)
    )

    wiki_topic_bonus = 0.0
    if candidate.provider == "wikipedia" and active_subject:
        if subject_title_hits == len(active_subject):
            wiki_topic_bonus = 5.5
        elif subject_title_hits >= 1 and subject_any_hits == len(active_subject):
            wiki_topic_bonus = 4.5

    citation_bonus = math.log1p(max(0, candidate.citation_count or 0)) * 0.45
    return (
        tier_score
        + full_text_bonus
        + phrase_bonus
        + title_overlap
        + core_overlap
        + off_topic_penalty
        + wiki_topic_bonus
        + citation_bonus
    )


@dataclass(frozen=True)
class ProviderSearchOutcome:
    items: list[DiscoveredSourceCandidate]
    provider_errors: list[str]


def search_curated_sources(
    query: str,
    *,
    scope: DiscoveryScope = "all",
    limit: int = 8,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> ProviderSearchOutcome:
    cleaned = " ".join(query.split()).strip()
    if not cleaned:
        return ProviderSearchOutcome(items=[], provider_errors=[])

    distilled = distill_search_query(cleaned)
    core_list = _core_query_tokens(distilled)
    subject_list = [tok for tok in core_list if tok not in _WIKI_QUALIFIERS]
    wiki_query = " ".join(subject_list[:4]) if len(subject_list) >= 2 else distilled

    timeout = min(float(settings.discovery_timeout_seconds if settings else 8.0), 8.0)
    mailto = settings.discovery_mailto if settings else None
    per_provider = min(max(limit, 3), 8)

    tasks: dict[str, Any] = {}
    if scope in {"all", "scholarly"}:
        tasks["openalex"] = lambda: search_openalex(
            distilled, limit=per_provider, timeout_seconds=timeout, mailto=mailto, client=client
        )
        tasks["crossref"] = lambda: search_crossref(
            distilled, limit=per_provider, timeout_seconds=timeout, mailto=mailto, client=client
        )
        tasks["arxiv"] = lambda: search_arxiv(
            distilled, limit=min(per_provider, 5), timeout_seconds=timeout, client=client
        )
    if scope in {"all", "web"}:
        tasks["wikipedia"] = lambda: search_wikipedia(
            wiki_query, limit=min(per_provider, 4), timeout_seconds=timeout, client=client
        )
        tasks["news"] = lambda: search_reputable_news(
            wiki_query, limit=min(per_provider, 4), timeout_seconds=timeout, client=client
        )

    raw_items: list[DiscoveredSourceCandidate] = []
    errors: list[str] = []

    if len(tasks) == 1:
        name, fn = next(iter(tasks.items()))
        try:
            raw_items.extend(fn())
        except Exception as exc:
            logger.warning("Discovery provider %s failed: %s", name, exc)
            errors.append(f"{name} is temporarily unavailable")
    else:
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {name: pool.submit(fn) for name, fn in tasks.items()}
            for name, future in futures.items():
                try:
                    raw_items.extend(future.result())
                except Exception as exc:
                    logger.warning("Discovery provider %s failed: %s", name, exc)
                    errors.append(f"{name} is temporarily unavailable")

    by_doi: dict[str, DiscoveredSourceCandidate] = {}
    by_title: dict[str, DiscoveredSourceCandidate] = {}
    deduped: list[DiscoveredSourceCandidate] = []

    for candidate in raw_items:
        doi = normalize_doi(candidate.doi)
        tkey = _title_key(candidate.title)
        match = (by_doi.get(doi) if doi else None) or (by_title.get(tkey) if tkey else None)
        if match is None:
            if doi:
                by_doi[doi] = candidate
            if tkey:
                by_title[tkey] = candidate
            deduped.append(candidate)
        else:
            merged = _merge_candidates(match, candidate)
            idx = deduped.index(match)
            deduped[idx] = merged
            if doi:
                by_doi[doi] = merged
            if merged.doi:
                by_doi[merged.doi] = merged
            if tkey:
                by_title[tkey] = merged

    core_terms = set(core_list) or set(_TOKEN_RE.findall(cleaned.lower()))
    subject_terms = set(subject_list)
    subject_phrase = wiki_query.lower() if len(subject_list) >= 2 else ""
    deduped.sort(
        key=lambda item: _score_candidate(item, core_terms, subject_terms, subject_phrase),
        reverse=True,
    )
    return ProviderSearchOutcome(items=deduped[:limit], provider_errors=errors)
