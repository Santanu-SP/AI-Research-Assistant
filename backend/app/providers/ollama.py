"""Local Ollama LLM provider adapter (Local / Self-Hosted Mode)."""

from __future__ import annotations

from time import monotonic
import httpx

from app.providers.base import (
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ModelUnavailableError,
    ProviderOutageError,
    ProviderTimeoutError,
    TokenUsage,
    classify_http_error,
    post_json_with_client,
)


class OllamaProviderAdapter(LLMProviderAdapter):
    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        default_model: str = "qwen3.5:9b-q4_K_M",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = client

    def is_configured(self, api_key_override: str | None = None) -> bool:
        return bool(self.base_url)

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model_override or self.default_model
        payload = {
            "model": model,
            "system": request.system_prompt,
            "prompt": request.user_prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        url = f"{self.base_url}/api/generate"
        started = monotonic()
        try:
            response = post_json_with_client(
                self._client,
                url,
                json=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(self.provider_name, f"Ollama timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderOutageError(self.provider_name, f"Ollama unreachable: {exc}") from exc

        latency_ms = (monotonic() - started) * 1000.0
        if response.status_code == 404:
            raise ModelUnavailableError(self.provider_name, f"Ollama model {model} not installed", status_code=404)
        if response.status_code >= 400:
            raise classify_http_error(self.provider_name, response)

        data = response.json()
        content = str(data.get("response") or "").strip()
        if not content:
            raise ProviderOutageError(self.provider_name, "Ollama returned empty response")

        prompt_eval = int(data.get("prompt_eval_count") or 0)
        eval_count = int(data.get("eval_count") or 0)
        usage = TokenUsage(
            prompt_tokens=prompt_eval,
            completion_tokens=eval_count,
            total_tokens=prompt_eval + eval_count,
        )
        return LLMResponse(
            provider=self.provider_name,
            model=model,
            content=content,
            usage=usage,
            latency_ms=latency_ms,
            used_byok=False,
        )

