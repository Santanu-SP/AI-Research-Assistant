"""Small pure-ASGI middlewares: request ids, security headers, body limits.

They are written against raw ASGI rather than ``BaseHTTPMiddleware`` so that
streaming uploads are not buffered and background tasks keep working.
"""

from collections.abc import Awaitable, Callable, MutableMapping
import json
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.core.logging import request_id_var

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

logger = logging.getLogger("app.http")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


class RequestContextMiddleware:
    """Attach an ``X-Request-ID`` to every request, response and log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and len(incoming) <= 64 and incoming.isprintable() else uuid4().hex
        token = request_id_var.set(request_id)
        started = perf_counter()
        status_holder = {"status": 500}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "%s %s -> %s",
                scope.get("method"),
                scope.get("path"),
                status_holder["status"],
                extra={"duration_ms": round((perf_counter() - started) * 1000, 1)},
            )
            request_id_var.reset(token)


API_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)
API_CSP = b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """Add conservative security headers to every API response."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = str(scope.get("path", "")).startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in headers}
                for key, value in API_SECURITY_HEADERS:
                    if key not in present:
                        headers.append((key, value))
                # Swagger UI needs scripts, so docs pages skip the strict CSP.
                if not is_docs and b"content-security-policy" not in present:
                    headers.append((b"content-security-policy", API_CSP))
                if self.hsts:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Refuse oversized request bodies before any parser buffers them.

    Multipart uploads may be up to ``upload_limit`` bytes (the document limit
    plus room for multipart framing); every other body is capped at
    ``default_limit``. Both the declared ``Content-Length`` and the bytes
    actually streamed are enforced, so chunked requests cannot slip past.
    """

    def __init__(self, app: ASGIApp, *, default_limit: int, upload_limit: int) -> None:
        self.app = app
        self.default_limit = default_limit
        self.upload_limit = upload_limit

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "request_too_large",
                    "message": "The request body exceeds the allowed size",
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        content_type = (_header(scope, b"content-type") or "").lower()
        limit = self.upload_limit if content_type.startswith("multipart/") else self.default_limit
        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            # Parsers may wrap our signal in their own 400 response; once the
            # limit has been crossed, always answer with a clean 413 instead.
            nonlocal response_started
            if exceeded:
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await self._reject(send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not response_started:
            await self._reject(send)


class _BodyTooLarge(Exception):
    pass
