"""Unified LLM provider interface, request/response models, and error taxonomy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


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

