"""Google Gemini Flash LLM provider adapter (Secondary)."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic
import httpx

from app.providers.base import (
    InvalidRequestError,
    validate_model_name,
    AuthenticationError,
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ModelUnavailableError,
    ProviderOutageError,
    ProviderTimeoutError,
    RateLimitError,
    TokenUsage,
    classify_http_error,
    post_json_with_client,
)


class GeminiProviderAdapter(LLMProviderAdapter):
    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "gemini-3.8-flash",
        fallback_model: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
        primary_timeout_seconds: float | None = 8.0,
        fallback_cooldown_seconds: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.fallback_model = (fallback_model or "").strip() or None
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.primary_timeout_seconds = primary_timeout_seconds
        self.fallback_cooldown_seconds = max(0.0, float(fallback_cooldown_seconds))
        self._prefer_fallback_until: float = 0.0

    def is_configured(self, api_key_override: str | None = None) -> bool:
        return bool(api_key_override or self.api_key)

    def _generate_with_model(
        self,
        model: str,
        effective_key: str,
        request: LLMRequest,
    ) -> LLMResponse:
        payload = {
            "systemInstruction": {
                "parts": [{"text": request.system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        try:
            safe_model = validate_model_name(model, provider=self.provider_name)
        except ValueError as exc:
            raise InvalidRequestError(self.provider_name, str(exc), status_code=400) from exc
        headers = {
            "x-goog-api-key": effective_key,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/models/{safe_model}:generateContent"
        started = monotonic()
        try:
            response = post_json_with_client(
                self._client,
                url,
                headers=headers,
                json=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(self.provider_name, f"Request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderOutageError(self.provider_name, f"Network error: {exc}") from exc

        latency_ms = (monotonic() - started) * 1000.0
        if response.status_code >= 400:
            raise classify_http_error(self.provider_name, response)

        data = response.json()
        candidates = data.get("candidates") or []
        parts_text: list[str] = []
        if candidates:
            content_obj = candidates[0].get("content") or {}
            for part in content_obj.get("parts") or []:
                if part.get("text"):
                    parts_text.append(str(part["text"]))
        content = "\n".join(parts_text).strip()
        if not content:
            raise ProviderOutageError(self.provider_name, "Empty completion returned")

        usage_meta = data.get("usageMetadata") or {}
        usage = TokenUsage(
            prompt_tokens=int(usage_meta.get("promptTokenCount") or 0),
            completion_tokens=int(usage_meta.get("candidatesTokenCount") or 0),
            total_tokens=int(usage_meta.get("totalTokenCount") or 0),
        )
        return LLMResponse(
            provider=self.provider_name,
            model=model,
            content=content,
            usage=usage,
            latency_ms=latency_ms,
            used_byok=bool(request.api_key_override),
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        effective_key = request.api_key_override or self.api_key
        if not effective_key:
            raise AuthenticationError(self.provider_name, "Missing GEMINI_API_KEY")

        using_byok = bool(request.api_key_override)
        has_distinct_fallback = bool(
            request.model_override is None
            and self.fallback_model
            and self.fallback_model != self.default_model
        )
        if (
            has_distinct_fallback
            and request.allow_sticky_fallback
            and not using_byok
            and monotonic() < self._prefer_fallback_until
        ):
            assert self.fallback_model is not None
            return self._generate_with_model(self.fallback_model, effective_key, request)

        primary_model = request.model_override or self.default_model
        primary_timeout_cap = (
            request.primary_timeout_seconds
            if request.primary_timeout_seconds is not None
            else (self.primary_timeout_seconds if request.allow_sticky_fallback else None)
        )
        primary_request = (
            replace(request, timeout_seconds=min(request.timeout_seconds, primary_timeout_cap))
            if has_distinct_fallback and primary_timeout_cap is not None
            else request
        )
        try:
            return self._generate_with_model(primary_model, effective_key, primary_request)
        except (
            ModelUnavailableError,
            ProviderOutageError,
            ProviderTimeoutError,
            RateLimitError,
        ):
            if has_distinct_fallback:
                assert self.fallback_model is not None
                response = self._generate_with_model(self.fallback_model, effective_key, request)
                if (
                    request.allow_sticky_fallback
                    and not using_byok
                    and self.fallback_cooldown_seconds > 0
                ):
                    self._prefer_fallback_until = monotonic() + self.fallback_cooldown_seconds
                return response
            raise

