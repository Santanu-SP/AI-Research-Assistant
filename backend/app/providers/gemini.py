"""Google Gemini Flash LLM provider adapter (Secondary)."""

from __future__ import annotations

from time import monotonic
import httpx

from app.providers.base import (
    AuthenticationError,
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ProviderOutageError,
    ProviderTimeoutError,
    TokenUsage,
    classify_http_error,
)


class GeminiProviderAdapter(LLMProviderAdapter):
    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "gemini-3.8-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self._client = client

    def is_configured(self, api_key_override: str | None = None) -> bool:
        return bool(api_key_override or self.api_key)

    def generate(self, request: LLMRequest) -> LLMResponse:
        effective_key = request.api_key_override or self.api_key
        if not effective_key:
            raise AuthenticationError(self.provider_name, "Missing GEMINI_API_KEY")

        model = request.model_override or self.default_model
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
        headers = {
            "x-goog-api-key": effective_key,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/models/{model}:generateContent"
        started = monotonic()
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=request.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
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

