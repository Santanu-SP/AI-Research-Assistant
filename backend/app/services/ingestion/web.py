"""Website content ingestion using Jina Reader and BeautifulSoup with strict SSRF protection."""

from __future__ import annotations

from collections.abc import Callable
import ipaddress
import socket
from urllib.parse import urlparse
from uuid import UUID

from bs4 import BeautifulSoup
import httpx

from app.core.errors import AppError
from app.domain.documents import MetadataProvenance
from app.domain.ingestion import CanonicalMetadata, ParsedDocument, ParsedNode
from app.services.ingestion.pipeline import DocumentIngestionError, stable_node_id

BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
    }
)
STRIP_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "aside", "form", "iframe", "svg")


def _is_disallowed_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_public_url(
    url: str,
    *,
    resolver: Callable[[str], list[str]] | None = None,
) -> str:
    """Validate that a URL uses HTTP(S) and does not target private/internal hosts (SSRF protection)."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise AppError(
            "Only http:// and https:// URLs are permitted",
            status_code=400,
            code="invalid_source_url",
        )
    if parsed.username or parsed.password:
        raise AppError(
            "URLs containing embedded credentials are not permitted",
            status_code=400,
            code="unsafe_source_url",
        )
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise AppError(
            "A valid hostname is required in the URL",
            status_code=400,
            code="invalid_source_url",
        )
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".localhost")
    ):
        raise AppError(
            "Private or local network URLs are not permitted",
            status_code=400,
            code="ssrf_blocked_url",
        )

    # Check if hostname is a literal IP
    try:
        ipaddress.ip_address(hostname)
        if _is_disallowed_ip(hostname):
            raise AppError(
                "Private, loopback, or link-local IP addresses are not permitted",
                status_code=400,
                code="ssrf_blocked_url",
            )
        return raw
    except ValueError:
        pass

    # If a custom DNS resolver is supplied (or in standard validation), check resolved IPs
    if resolver is not None:
        resolved_ips = resolver(hostname)
        if not resolved_ips or any(_is_disallowed_ip(ip) for ip in resolved_ips):
            raise AppError(
                "The hostname resolves to a disallowed private or internal IP address",
                status_code=400,
                code="ssrf_blocked_url",
            )
    else:
        try:
            infos = socket.getaddrinfo(hostname, None)
            for info in infos:
                ip_str = str(info[4][0])
                if _is_disallowed_ip(ip_str):
                    raise AppError(
                        "The hostname resolves to a disallowed private or internal IP address",
                        status_code=400,
                        code="ssrf_blocked_url",
                    )
        except socket.gaierror:
            # In offline/sandboxed environments DNS resolution may not be available at registration time;
            # literal IPs and local hostnames are already blocked above.
            pass

    return raw


def extract_clean_html_sections(html: str) -> tuple[str | None, list[tuple[str | None, str]]]:
    """Extract page title and clean (section_heading, text) pairs from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split()).strip() or None

    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = title
    current_paragraphs: list[str] = []

    for element in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "table", "pre"]):
        name = element.name
        if name in {"h1", "h2", "h3", "h4"}:
            heading_text = " ".join(element.get_text(" ", strip=True).split()).strip()
            if heading_text:
                if current_paragraphs:
                    sections.append((current_heading, "\n\n".join(current_paragraphs)))
                    current_paragraphs = []
                current_heading = heading_text
                if title is None and name == "h1":
                    title = heading_text
        elif name == "table":
            rows = []
            for tr in element.find_all("tr"):
                cells = [
                    " ".join(td.get_text(" ", strip=True).split())
                    for td in tr.find_all(["th", "td"])
                ]
                if any(cells):
                    rows.append("| " + " | ".join(cells) + " |")
            if len(rows) >= 1:
                header_cols = rows[0].count("|") - 1
                if header_cols > 0:
                    sep = "| " + " | ".join(["---"] * header_cols) + " |"
                    table_md = "\n".join([rows[0], sep, *rows[1:]])
                else:
                    table_md = "\n".join(rows)
                current_paragraphs.append(table_md)
        else:
            text_val = " ".join(element.get_text(" ", strip=True).split()).strip()
            if len(text_val) >= 3:
                current_paragraphs.append(text_val)

    if current_paragraphs:
        sections.append((current_heading, "\n\n".join(current_paragraphs)))

    if not sections:
        fallback_text = " ".join(root.get_text(" ", strip=True).split()).strip()
        if fallback_text:
            sections.append((title, fallback_text))

    return title, sections


def chunk_web_sections(
    document_id: UUID,
    sections: list[tuple[str | None, str]],
    *,
    chunk_size: int = 1500,
    overlap: int = 150,
    page_title: str | None = None,
    source_url: str | None = None,
) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    for heading, body in sections:
        text = body.strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            piece = text[start:end].strip()
            if piece:
                idx = len(nodes)
                section_path = [p for p in (page_title, heading) if p]
                # Deduplicate if page_title == heading
                if len(section_path) == 2 and section_path[0] == section_path[1]:
                    section_path = [section_path[0]]
                meta: dict[str, object] = {
                    "content_kind": "table" if piece.startswith("| ") else "web_section",
                }
                if source_url:
                    meta["source_url"] = source_url
                nodes.append(
                    ParsedNode(
                        node_id=stable_node_id(document_id, idx, piece),
                        text=piece,
                        chunk_index=idx,
                        page=1,
                        page_end=1,
                        section=heading or page_title,
                        section_path=section_path,
                        token_count=len(piece.split()),
                        metadata=meta,
                    )
                )
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
    return nodes


class WebsiteIngestionAdapter:
    """Extracts readable web content via Jina Reader or clean HTML parsing with SSRF protection."""

    def __init__(
        self,
        *,
        jina_reader_base_url: str | None = "https://r.jina.ai",
        jina_api_key: str | None = None,
        chunk_size: int = 1500,
        overlap: int = 150,
        client: httpx.Client | None = None,
        dns_resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.jina_reader_base_url = (jina_reader_base_url or "").rstrip("/")
        self.jina_api_key = jina_api_key
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(25.0, connect=5.0),
            follow_redirects=False,
        )
        self._dns_resolver = dns_resolver

    def parse_url(
        self,
        url: str,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        validated = validate_public_url(url, resolver=self._dns_resolver)
        provenance_source = MetadataProvenance.EXTRACTED
        title: str | None = None
        sections: list[tuple[str | None, str]] = []

        # 1. Try Jina Reader if configured
        if self.jina_reader_base_url:
            jina_url = f"{self.jina_reader_base_url}/{validated}"
            headers = {"Accept": "text/plain"}
            if self.jina_api_key:
                headers["Authorization"] = f"Bearer {self.jina_api_key}"
            try:
                resp = self._client.get(jina_url, headers=headers)
                if resp.status_code == 200 and resp.text.strip():
                    raw_md = resp.text.strip()
                    lines = raw_md.splitlines()
                    for line in lines[:5]:
                        if line.lower().startswith("title:"):
                            title = line.split(":", 1)[1].strip() or None
                            break
                    sections = [(title or "Web Content", raw_md)]
                    provenance_source = MetadataProvenance.JINA
            except httpx.HTTPError:
                pass

        # 2. Fallback to direct HTML fetch
        if not sections:
            try:
                resp = self._client.get(
                    validated,
                    headers={"User-Agent": "AIResearchAssistantBot/1.0"},
                )
                if resp.status_code in {301, 302, 303, 307, 308}:
                    redirect_target = resp.headers.get("location", "")
                    validate_public_url(redirect_target, resolver=self._dns_resolver)
                    resp = self._client.get(
                        redirect_target,
                        headers={"User-Agent": "AIResearchAssistantBot/1.0"},
                    )
                resp.raise_for_status()
            except AppError:
                raise
            except httpx.HTTPError as exc:
                raise DocumentIngestionError(
                    "The website page could not be retrieved",
                    code="website_unreachable",
                    status_code=422,
                ) from exc

            title, sections = extract_clean_html_sections(resp.text)

        resolved_title = title or urlparse(validated).netloc
        nodes = chunk_web_sections(
            document_id,
            sections,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
            page_title=resolved_title,
            source_url=validated,
        )
        if not nodes:
            raise DocumentIngestionError(
                "The webpage contains no extractable text content",
                code="empty_webpage_content",
                status_code=422,
            )

        return ParsedDocument(
            document_id=document_id,
            metadata=CanonicalMetadata(
                title=resolved_title,
                values={"source_url": validated},
                provenance={"title": provenance_source},
            ),
            page_count=1,
            parser_name="jina-reader" if provenance_source is MetadataProvenance.JINA else "beautifulsoup-html",
            parser_version="1.0",
            ingestion_version=f"{ingestion_version}:web",
            nodes=nodes,
        )

    def parse(
        self,
        path,
        *,
        document_id: UUID,
        ingestion_version: str,
    ) -> ParsedDocument:
        url = path.read_text(encoding="utf-8").strip()
        return self.parse_url(url, document_id=document_id, ingestion_version=ingestion_version)

