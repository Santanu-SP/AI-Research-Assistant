"""Unified LLM provider interface, request/response models, and error taxonomy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from threading import Lock
from typing import Any

import httpx


_HTTP_CLIENT_LOCK = Lock()
_SHARED_HTTP_CLIENT: httpx.Client | None = None
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_SNAPSHOTS: dict[tuple[str, str], ProviderRateLimitSnapshot] = {}


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


# Short, safe failure types the UI can explain in plain words.
MODEL_ERROR_QUOTA = "quota"
MODEL_ERROR_AUTH = "auth"
MODEL_ERROR_TIMEOUT = "timeout"
MODEL_ERROR_UNAVAILABLE = "unavailable"
MODEL_ERROR_OTHER = "other"


def model_error_type(exc: Exception) -> str:
    """Map a provider error to one of the short failure types above."""
    if isinstance(exc, RateLimitError):
        return MODEL_ERROR_QUOTA
    if isinstance(exc, AuthenticationError):
        return MODEL_ERROR_AUTH
    if isinstance(exc, ProviderTimeoutError):
        return MODEL_ERROR_TIMEOUT
    if isinstance(exc, (ModelUnavailableError, ProviderOutageError)):
        return MODEL_ERROR_UNAVAILABLE
    return MODEL_ERROR_OTHER


_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    # Google's newer key format starts with "AQ.".
    re.compile(r"\bAQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\b(?:sk|pk|gsk|csk|xai)-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|key|token|secret)\s*[=:]\s*)[^\s&,;\"']{6,}"),
)


def redact_secrets(text: str) -> str:
    """Hide anything that looks like an API key before a message is stored or shown."""
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(
            lambda match: (match.group(1) if match.groups() else "") + "[hidden]",
            cleaned,
        )
    return cleaned


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


@dataclass(frozen=True)
class ProviderRateLimitSnapshot:
    """Latest rate-limit telemetry parsed from a provider's HTTP response headers."""

    provider: str
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens: str | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def key_scope_fingerprint(api_key: str | None, *, is_byok: bool) -> str:
    """Return a non-secret bucket key separating shared server keys from user BYOK keys."""
    if not is_byok or not api_key:
        return "shared"
    digest = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()[:16]
    return f"byok:{digest}"


def _header_value(headers: Mapping[str, str], *names: str) -> str | None:
    if isinstance(headers, httpx.Headers):
        for name in names:
            val = headers.get(name)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    for name in names:
        val = lowered.get(name.lower())
        if val is not None and val.strip():
            return val.strip()
    return None


def _parse_header_int(headers: Mapping[str, str], *names: str) -> int | None:
    raw = _header_value(headers, *names)
    if raw is None:
        return None
    try:
        parsed = int(float(raw))
        return parsed if parsed >= 0 else None
    except ValueError:
        return None


def capture_rate_limit_headers(
    provider: str,
    headers: Mapping[str, str],
    *,
    api_key: str | None = None,
    is_byok: bool = False,
) -> ProviderRateLimitSnapshot | None:
    """Parse standard OpenAI/Groq/OpenRouter/Anthropic rate-limit headers if present."""
    limit_requests = _parse_header_int(
        headers,
        "x-ratelimit-limit-requests",
        "anthropic-ratelimit-requests-limit",
    )
    remaining_requests = _parse_header_int(
        headers,
        "x-ratelimit-remaining-requests",
        "anthropic-ratelimit-requests-remaining",
    )
    reset_requests = _header_value(
        headers,
        "x-ratelimit-reset-requests",
        "anthropic-ratelimit-requests-reset",
        "retry-after",
    )
    limit_tokens = _parse_header_int(
        headers,
        "x-ratelimit-limit-tokens",
        "anthropic-ratelimit-tokens-limit",
    )
    remaining_tokens = _parse_header_int(
        headers,
        "x-ratelimit-remaining-tokens",
        "anthropic-ratelimit-tokens-remaining",
    )
    reset_tokens = _header_value(
        headers,
        "x-ratelimit-reset-tokens",
        "anthropic-ratelimit-tokens-reset",
    )
    if (
        limit_requests is None
        and remaining_requests is None
        and limit_tokens is None
        and remaining_tokens is None
    ):
        return None

    norm_provider = (provider or "").strip().lower()
    snapshot = ProviderRateLimitSnapshot(
        provider=norm_provider,
        limit_requests=limit_requests,
        remaining_requests=remaining_requests,
        reset_requests=reset_requests,
        limit_tokens=limit_tokens,
        remaining_tokens=remaining_tokens,
        reset_tokens=reset_tokens,
    )
    scope = key_scope_fingerprint(api_key, is_byok=is_byok)
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_SNAPSHOTS[(norm_provider, scope)] = snapshot
    return snapshot


def get_rate_limit_snapshot(
    provider: str,
    *,
    api_key: str | None = None,
    is_byok: bool = False,
    max_age_seconds: float = 3600.0,
) -> ProviderRateLimitSnapshot | None:
    """Return the latest non-stale rate-limit header snapshot for ``(provider, key_scope)``."""
    norm_provider = (provider or "").strip().lower()
    scope = key_scope_fingerprint(api_key, is_byok=is_byok)
    with _RATE_LIMIT_LOCK:
        snapshot = _RATE_LIMIT_SNAPSHOTS.get((norm_provider, scope))
    if snapshot is None:
        return None
    age = (datetime.now(timezone.utc) - snapshot.captured_at).total_seconds()
    if age > max_age_seconds:
        return None
    return snapshot


def clear_rate_limit_snapshots() -> None:
    """Clear in-memory rate-limit header snapshots (for tests)."""
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_SNAPSHOTS.clear()

