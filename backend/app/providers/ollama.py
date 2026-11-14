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


def _pick_installed_ollama_model(models: list[str], configured_model: str | None) -> str | None:
    if not models:
        return None
    if configured_model:
        if configured_model in models:
            return configured_model
        configured_base = configured_model.split(":", 1)[0]
        for candidate in models:
            if candidate.split(":", 1)[0] == configured_base:
                return candidate
    non_embed = [name for name in models if "embed" not in name.lower()]
    if non_embed:
        return non_embed[0]
    return models[0]


def probe_ollama_models(
    base_url: str,
    configured_model: str | None = None,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = 1.5,
) -> tuple[bool, list[str], str | None]:
    """Check whether local Ollama is reachable and list installed models."""
    cleaned_base = (base_url or "").strip().rstrip("/")
    if not cleaned_base:
        return False, [], None
    url = f"{cleaned_base}/api/tags"
    try:
        if client is not None:
            response = client.get(url, timeout=timeout_seconds)
        else:
            with httpx.Client(timeout=timeout_seconds) as temp_client:
                response = temp_client.get(url)
    except httpx.HTTPError:
        return False, [], None
    if response.status_code >= 400:
        return False, [], None
    try:
        data = response.json()
    except ValueError:
        return False, [], None
    raw_models = data.get("models") or []
    models: list[str] = []
    for item in raw_models:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
    resolved = _pick_installed_ollama_model(models, configured_model)
    # Require at least one non-embedding model to report usable generation availability,
    # or fall back to any reported model if none are clearly tagged as embeddings.
    generative = [name for name in models if "embed" not in name.lower()]
    available = bool(generative)
    return available, models, resolved if available else None


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

    def _post_generate(self, payload: dict[str, object], timeout_seconds: float) -> httpx.Response:
        url = f"{self.base_url}/api/generate"
        return post_json_with_client(
            self._client,
            url,
            json=payload,
            timeout_seconds=timeout_seconds,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model_override or self.default_model
        payload: dict[str, object] = {
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
        started = monotonic()
        try:
            response = self._post_generate(payload, request.timeout_seconds)
            if response.status_code == 400 and "think" in payload:
                payload_without_think = {k: v for k, v in payload.items() if k != "think"}
                response = self._post_generate(payload_without_think, request.timeout_seconds)
            if response.status_code == 404 and not request.model_override:
                available, _, fallback_model = probe_ollama_models(
                    self.base_url,
                    model,
                    client=self._client,
                    timeout_seconds=min(request.timeout_seconds, 2.0),
                )
                if available and fallback_model and fallback_model != model:
                    model = fallback_model
                    fallback_payload = dict(payload)
                    fallback_payload["model"] = model
                    response = self._post_generate(fallback_payload, request.timeout_seconds)
                    if response.status_code == 400 and "think" in fallback_payload:
                        fallback_without_think = {
                            k: v for k, v in fallback_payload.items() if k != "think"
                        }
                        response = self._post_generate(
                            fallback_without_think, request.timeout_seconds
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

