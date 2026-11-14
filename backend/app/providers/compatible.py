"""Additional cloud LLM provider adapters (Groq, OpenAI, Grok, Claude)."""

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
    post_json_with_client,
)


class OpenAICompatibleProviderAdapter(LLMProviderAdapter):
    """Shared adapter for OpenAI Chat Completions compatible cloud providers."""

    provider_name = "openai"
    missing_key_env = "OPENAI_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
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
            raise AuthenticationError(self.provider_name, f"Missing {self.missing_key_env}")

        model = request.model_override or self.default_model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
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
        choices = data.get("choices") or []
        content = ""
        if choices:
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "").strip()
        if not content:
            raise ProviderOutageError(self.provider_name, "Empty completion returned")

        usage_raw = data.get("usage") or {}
        usage = TokenUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            total_tokens=int(usage_raw.get("total_tokens") or 0),
        )
        return LLMResponse(
            provider=self.provider_name,
            model=str(data.get("model") or model),
            content=content,
            usage=usage,
            latency_ms=latency_ms,
            used_byok=bool(request.api_key_override),
        )


class GroqProviderAdapter(OpenAICompatibleProviderAdapter):
    provider_name = "groq"
    missing_key_env = "GROQ_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            base_url=base_url,
            client=client,
        )


class OpenAIProviderAdapter(OpenAICompatibleProviderAdapter):
    provider_name = "openai"
    missing_key_env = "OPENAI_API_KEY"


class GrokProviderAdapter(OpenAICompatibleProviderAdapter):
    provider_name = "grok"
    missing_key_env = "GROK_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "grok-3-mini-fast",
        base_url: str = "https://api.x.ai/v1",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            base_url=base_url,
            client=client,
        )


class ClaudeProviderAdapter(LLMProviderAdapter):
    provider_name = "claude"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "claude-3-5-haiku-latest",
        base_url: str = "https://api.anthropic.com/v1",
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
            raise AuthenticationError(self.provider_name, "Missing CLAUDE_API_KEY")

        model = request.model_override or self.default_model
        payload = {
            "model": model,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        headers = {
            "x-api-key": effective_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/messages"
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
        blocks = data.get("content") or []
        parts = [
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        content = "\n".join(part for part in parts if part).strip()
        if not content:
            raise ProviderOutageError(self.provider_name, "Empty completion returned")

        usage_raw = data.get("usage") or {}
        prompt_tokens = int(usage_raw.get("input_tokens") or 0)
        completion_tokens = int(usage_raw.get("output_tokens") or 0)
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        return LLMResponse(
            provider=self.provider_name,
            model=str(data.get("model") or model),
            content=content,
            usage=usage,
            latency_ms=latency_ms,
            used_byok=bool(request.api_key_override),
        )
