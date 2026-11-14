"""Unified LLM provider interface, request/response models, and error taxonomy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from threading import Lock
from typing import Any

import httpx


_HTTP_CLIENT_LOCK = Lock()
_SHARED_HTTP_CLIENT: httpx.Client | None = None


def get_shared_http_client() -> httpx.Client:
    """Return a process-wide pooled httpx.Client to reuse TLS keep-alive connections."""
    global _SHARED_HTTP_CLIENT
    with _HTTP_CLIENT_LOCK:
        if _SHARED_HTTP_CLIENT is None or _SHARED_HTTP_CLIENT.is_closed:
            _SHARED_HTTP_CLIENT = httpx.Client(
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=16, max_connections=32),
            )
        return _SHARED_HTTP_CLIENT


def post_json_with_client(
    client: httpx.Client | None,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any],
    timeout_seconds: float,
) -> httpx.Response:
    """POST JSON via the injected test client or the pooled shared client."""
    active_client = client if client is not None else get_shared_http_client()
    return active_client.post(
        url,
        headers=headers,
        json=json,
        timeout=timeout_seconds,
    )


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    max_tokens: int = 700
    temperature: float = 0.1
    timeout_seconds: float = 45.0
    model_override: str | None = None
    api_key_override: str | None = None
    provider_timeout_seconds: float | None = None
    primary_timeout_seconds: float | None = None
    allow_sticky_fallback: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    model: str
    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    used_byok: bool = False
    fallback_attempts: int = 0


class ProviderError(Exception):
    """Base error raised by LLM provider adapters."""

    retryable: bool = False
    should_fallback: bool = True
    trips_circuit: bool = True

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class RateLimitError(ProviderError):
    """429 rate limit or quota exhaustion error."""

    retryable = False
    should_fallback = True
    trips_circuit = True


class AuthenticationError(ProviderError):
    """401/403 missing or invalid API key."""

    retryable = False
    should_fallback = True
    trips_circuit = False


class InvalidRequestError(ProviderError):
    """400/422 malformed request payload."""

    retryable = False
    should_fallback = False
    trips_circuit = False


class ModelUnavailableError(ProviderError):
    """404 or deprecated/unavailable model."""

    retryable = False
    should_fallback = True
    trips_circuit = True


class ProviderTimeoutError(ProviderError):
    """Request timed out waiting for LLM provider."""

    retryable = False
    should_fallback = True
    trips_circuit = True


class ProviderOutageError(ProviderError):
    """5xx server error or network connectivity error."""

    retryable = True
    should_fallback = True
    trips_circuit = True


def classify_http_error(provider: str, response: httpx.Response) -> ProviderError:
    status = response.status_code
    retry_after: float | None = None
    ra_header = response.headers.get("retry-after")
    if ra_header:
        try:
            retry_after = float(ra_header)
        except ValueError:
            retry_after = None

    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                detail = str(err.get("message") or err.get("code") or "")
            elif err:
                detail = str(err)
            elif payload.get("message"):
                detail = str(payload.get("message"))
    except Exception:
        detail = response.text[:200] if response.text else ""

    msg = detail or f"HTTP {status}"
    if status == 429:
        return RateLimitError(
            provider,
            f"Rate limit or quota exceeded: {msg}",
            status_code=status,
            retry_after_seconds=retry_after,
        )
    if status in (401, 403):
        return AuthenticationError(
            provider,
            f"Authentication failed: {msg}",
            status_code=status,
        )
    if status == 404:
        return ModelUnavailableError(
            provider,
            f"Model unavailable: {msg}",
            status_code=status,
        )
    if status in (400, 422):
        lower = msg.lower()
        if "quota" in lower or "rate" in lower or "resource_exhausted" in lower:
            return RateLimitError(provider, msg, status_code=status)
        if "api_key" in lower or "key not valid" in lower:
            return AuthenticationError(provider, msg, status_code=status)
        return InvalidRequestError(
            provider,
            f"Invalid request: {msg}",
            status_code=status,
        )
    if status == 504 or status == 408:
        return ProviderTimeoutError(
            provider,
            f"Provider timed out: {msg}",
            status_code=status,
        )
    return ProviderOutageError(
        provider,
        f"Provider outage (HTTP {status}): {msg}",
        status_code=status,
    )


class LLMProviderAdapter(ABC):
    provider_name: str
    default_model: str

    @abstractmethod
    def is_configured(self, api_key_override: str | None = None) -> bool:
        """Return True if this provider has credentials or local endpoint configured."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion and return a unified LLMResponse."""


MAX_MODEL_NAME_LENGTH = 160
_GEMINI_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_GENERAL_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def validate_model_name(model_name: str, *, provider: str | None = None) -> str:
    """Validate and normalize a user-supplied or configured model ID.

    Prevents URL path injection, query/fragment delimiters (``?``, ``#``, ``%``),
    whitespace, and path traversal (``..``) before hitting provider endpoints.
    """
    cleaned = (model_name or "").strip()
    if not cleaned:
        raise ValueError("Model name must not be empty.")
    if len(cleaned) > MAX_MODEL_NAME_LENGTH:
        raise ValueError(f"Model name must be at most {MAX_MODEL_NAME_LENGTH} characters.")
    if ".." in cleaned or "//" in cleaned or cleaned.endswith(("/", ".", ":")):
        raise ValueError("Model name contains unsafe path or delimiter sequences.")

    norm_provider = (provider or "").strip().lower() or None
    pattern = _GEMINI_MODEL_NAME_RE if norm_provider == "gemini" else _GENERAL_MODEL_NAME_RE
    if not pattern.fullmatch(cleaned):
        if norm_provider == "gemini":
            raise ValueError(
                "Gemini model names may contain only letters, digits, '.', '_', and '-'."
            )
        raise ValueError(
            "Model names may contain only letters, digits, '.', '_', '-', ':', and '/'."
        )
    return cleaned

