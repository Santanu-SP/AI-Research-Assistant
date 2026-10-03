"""Central SSRF-protected fetch boundary for user-provided research URLs."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.errors import AppError


Resolver = Callable[[str, int], Awaitable[Sequence[str]]]
REDIRECT_CODES = {301, 302, 303, 307, 308}
ACCEPTED_CONTENT_TYPES = {
    "text/html": (".html", "text/html"),
    "application/xhtml+xml": (".html", "text/html"),
    "application/pdf": (".pdf", "application/pdf"),
}


@dataclass(frozen=True)
class FetchedResource:
    final_url: str
    content_type: str
    extension: str
    content: bytes
    checksum: str


async def system_resolver(host: str, port: int) -> Sequence[str]:
    import asyncio

    loop = asyncio.get_running_loop()
    records = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM),
    )
    return sorted({record[4][0] for record in records})


def _safe_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global


async def validate_public_url(url: str, resolver: Resolver = system_resolver) -> str:
    candidate = url.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise AppError(
            "The source URL is invalid",
            status_code=422,
            code="invalid_source_url",
        ) from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise AppError(
            "Only HTTP and HTTPS source URLs are supported",
            status_code=422,
            code="unsupported_url_scheme",
        )
    if not parsed.hostname or parsed.username or parsed.password:
        raise AppError(
            "The source URL is invalid",
            status_code=422,
            code="invalid_source_url",
        )
    effective_port = port or (443 if parsed.scheme.casefold() == "https" else 80)
    try:
        addresses = await resolver(parsed.hostname, effective_port)
    except (OSError, socket.gaierror) as exc:
        raise AppError(
            "The source URL host could not be resolved",
            status_code=422,
            code="source_host_unresolved",
        ) from exc
    if not addresses or any(not _safe_address(address) for address in addresses):
        raise AppError(
            "The source URL points to a blocked network address",
            status_code=422,
            code="unsafe_source_url",
        )
    # Fragments are browser-only and must not create distinct source identities.
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc, parsed.path or "/", parsed.query, ""))


class SecureUrlFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        timeout: float,
        connect_timeout: float,
        max_bytes: int,
        max_redirects: int,
        resolver: Resolver = system_resolver,
    ) -> None:
        self.client = client
        self.timeout = httpx.Timeout(timeout, connect=connect_timeout)
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolver = resolver

    async def fetch(self, url: str) -> FetchedResource:
        current = url
        for redirect_count in range(self.max_redirects + 1):
            current = await validate_public_url(current, self.resolver)
            try:
                async with self.client.stream(
                    "GET",
                    current,
                    timeout=self.timeout,
                    follow_redirects=False,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/pdf",
                        "User-Agent": "AI-Research-Assistant/0.1",
                    },
                ) as response:
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("Location")
                        if not location:
                            raise AppError(
                                "The source URL returned an invalid redirect",
                                status_code=422,
                                code="invalid_source_redirect",
                            )
                        if redirect_count >= self.max_redirects:
                            raise AppError(
                                "The source URL exceeded the redirect limit",
                                status_code=422,
                                code="source_redirect_limit",
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code == 429:
                        raise AppError(
                            "The source website rate limited this request",
                            status_code=503,
                            code="source_rate_limited",
                        )
                    if response.status_code >= 400:
                        raise AppError(
                            "The source URL could not be downloaded",
                            status_code=422,
                            code="source_fetch_failed",
                        )
                    content_type = response.headers.get("Content-Type", "")
                    content_type = content_type.split(";", 1)[0].strip().casefold()
                    supported = ACCEPTED_CONTENT_TYPES.get(content_type)
                    if supported is None:
                        raise AppError(
                            "The source URL returned an unsupported content type",
                            status_code=415,
                            code="unsupported_source_content_type",
                        )
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            if int(content_length) > self.max_bytes:
                                raise AppError(
                                    "The downloaded source exceeds the configured size limit",
                                    status_code=413,
                                    code="source_too_large",
                                )
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    size = 0
                    digest = hashlib.sha256()
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise AppError(
                                "The downloaded source exceeds the configured size limit",
                                status_code=413,
                                code="source_too_large",
                            )
                        digest.update(chunk)
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise AppError(
                            "The source URL returned empty content",
                            status_code=422,
                            code="empty_source",
                        )
                    extension, normalized_type = supported
                    if extension == ".pdf" and b"%PDF-" not in content[:1024]:
                        raise AppError(
                            "The source URL did not return a valid PDF",
                            status_code=422,
                            code="invalid_remote_pdf",
                        )
                    if extension == ".html":
                        try:
                            content.decode("utf-8")
                        except UnicodeDecodeError as exc:
                            raise AppError(
                                "The source webpage must use UTF-8 encoding",
                                status_code=422,
                                code="invalid_remote_html",
                            ) from exc
                    return FetchedResource(
                        final_url=str(response.url),
                        content_type=normalized_type,
                        extension=extension,
                        content=content,
                        checksum=digest.hexdigest(),
                    )
            except httpx.TimeoutException as exc:
                raise AppError(
                    "The source URL timed out",
                    status_code=504,
                    code="source_fetch_timeout",
                ) from exc
            except httpx.HTTPError as exc:
                raise AppError(
                    "The source URL could not be downloaded",
                    status_code=502,
                    code="source_fetch_failed",
                ) from exc
        raise AppError(
            "The source URL exceeded the redirect limit",
            status_code=422,
            code="source_redirect_limit",
        )
