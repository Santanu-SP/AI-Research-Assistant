"""Centralized LLM Router with cascading fallback, circuit breakers, health & quota tracking."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from threading import RLock
from time import monotonic, sleep
from typing import Callable

from app.core.config import Settings
from app.core.errors import AppError
from app.providers.base import (
    InvalidRequestError,
    LLMProviderAdapter,
    LLMRequest,
    LLMResponse,
    ProviderError,
)
from app.providers.cerebras import CerebrasProviderAdapter
from app.providers.compatible import (
    ClaudeProviderAdapter,
    GrokProviderAdapter,
    GroqProviderAdapter,
    OpenAIProviderAdapter,
)
from app.providers.gemini import GeminiProviderAdapter
from app.providers.mistral import MistralProviderAdapter
from app.providers.ollama import OllamaProviderAdapter
from app.providers.openrouter import OpenRouterProviderAdapter

logger = logging.getLogger(__name__)

_PROVIDER_ALIASES: dict[str, str] = {
    "anthropic": "claude",
    "xai": "grok",
}


def _normalize_provider(name: str) -> str:
    cleaned = name.strip().lower()
    return _PROVIDER_ALIASES.get(cleaned, cleaned)


@dataclass
class ProviderHealth:
    provider: str
    circuit_state: str = "closed"  # closed | open | half_open
    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    cooldown_until: float | None = None
    tokens_used_today: int = 0
    daily_token_budget: int = 1_000_000
    budget_day: str = ""
    last_error: str | None = None


class CentralizedLLMRouter:
    """Routes LLM generation across Cerebras -> Gemini Flash -> Mistral -> OpenRouter (+ Ollama)."""

    def __init__(
        self,
        adapters: list[LLMProviderAdapter],
        *,
        catalog: dict[str, LLMProviderAdapter] | None = None,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        max_transient_retries: int = 1,
        retry_backoff_seconds: float = 0.25,
        daily_token_budget: int = 1_000_000,
        provider_timeout_seconds: float | None = None,
        on_event: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.adapters = list(adapters)
        self.catalog: dict[str, LLMProviderAdapter] = (
            dict(catalog)
            if catalog is not None
            else {adapter.provider_name: adapter for adapter in self.adapters}
        )
        for adapter in self.adapters:
            self.catalog.setdefault(adapter.provider_name, adapter)
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1.0, cooldown_seconds)
        self.max_transient_retries = max(0, max_transient_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.daily_token_budget = max(1000, daily_token_budget)
        self.provider_timeout_seconds = provider_timeout_seconds
        self._on_event = on_event
        self._lock = RLock()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._health: dict[str, ProviderHealth] = {
            adapter.provider_name: ProviderHealth(
                provider=adapter.provider_name,
                daily_token_budget=self.daily_token_budget,
                budget_day=today,
            )
            for adapter in self.catalog.values()
        }

    def get_health_snapshot(self) -> dict[str, dict[str, object]]:
        now = monotonic()
        with self._lock:
            result: dict[str, dict[str, object]] = {}
            for name, state in self._health.items():
                circuit = state.circuit_state
                if circuit == "open" and state.cooldown_until is not None and now >= state.cooldown_until:
                    circuit = "half_open"
                result[name] = {
                    "provider": state.provider,
                    "circuit_state": circuit,
                    "consecutive_failures": state.consecutive_failures,
                    "success_count": state.success_count,
                    "failure_count": state.failure_count,
                    "avg_latency_ms": round(state.avg_latency_ms, 2),
                    "tokens_used_today": state.tokens_used_today,
                    "daily_token_budget": state.daily_token_budget,
                    "last_error": state.last_error,
                }
            return result

    def _is_provider_available(self, name: str, *, using_byok: bool) -> bool:
        if using_byok:
            # User-supplied keys carry their own quota and must not be blocked
            # by shared system circuit breakers or shared daily token limits.
            return True
        now = monotonic()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            state = self._health.get(name)
            if state is None:
                return True
            if state.budget_day != today:
                state.budget_day = today
                state.tokens_used_today = 0
            if state.tokens_used_today >= state.daily_token_budget:
                return False
            if state.circuit_state == "open":
                if state.cooldown_until is not None and now >= state.cooldown_until:
                    state.circuit_state = "half_open"
                    return True
                return False
            return True

    def _record_success(self, response: LLMResponse) -> None:
        if response.used_byok:
            # A user's BYOK key succeeding must not close/reset a tripped system breaker
            # or charge tokens against the system pool.
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            state = self._health.setdefault(
                response.provider,
                ProviderHealth(provider=response.provider, daily_token_budget=self.daily_token_budget, budget_day=today),
            )
            if state.budget_day != today:
                state.budget_day = today
                state.tokens_used_today = 0
            state.circuit_state = "closed"
            state.consecutive_failures = 0
            state.cooldown_until = None
            state.success_count += 1
            state.tokens_used_today += max(0, response.usage.total_tokens)
            if state.avg_latency_ms == 0.0:
                state.avg_latency_ms = response.latency_ms
            else:
                state.avg_latency_ms = 0.8 * state.avg_latency_ms + 0.2 * response.latency_ms

    def _record_failure(
        self,
        provider: str,
        exc: ProviderError,
        *,
        using_byok: bool = False,
    ) -> None:
        if using_byok:
            # Never poison or trip shared system circuit breakers from a user's BYOK key.
            return
        now = monotonic()
        with self._lock:
            state = self._health.setdefault(
                provider,
                ProviderHealth(provider=provider, daily_token_budget=self.daily_token_budget),
            )
            state.failure_count += 1
            state.last_error = exc.message
            if exc.trips_circuit:
                state.consecutive_failures += 1
                if state.consecutive_failures >= self.failure_threshold:
                    state.circuit_state = "open"
                    cooldown = exc.retry_after_seconds or self.cooldown_seconds
                    state.cooldown_until = now + max(1.0, float(cooldown))

    def _build_ordered_adapters(
        self,
        *,
        user_keys: dict[str, str],
        preferred: str | None,
        local_fallback_enabled: bool | None,
    ) -> list[LLMProviderAdapter]:
        ordered: list[LLMProviderAdapter] = []
        seen: set[str] = set()

        def _append(adapter: LLMProviderAdapter | None) -> None:
            if adapter is None or adapter.provider_name in seen:
                return
            seen.add(adapter.provider_name)
            ordered.append(adapter)

        if preferred:
            _append(
                self.catalog.get(preferred)
                or next((a for a in self.adapters if a.provider_name == preferred), None)
            )

        for adapter in self.adapters:
            if adapter.provider_name == "ollama" and local_fallback_enabled is not None:
                continue
            _append(adapter)

        for name, adapter in self.catalog.items():
            if name == "ollama":
                continue
            if name in user_keys:
                _append(adapter)

        if local_fallback_enabled is True:
            _append(self.catalog.get("ollama"))
        elif local_fallback_enabled is False and preferred != "ollama":
            ordered = [a for a in ordered if a.provider_name != "ollama"]

        return ordered

    def generate(
        self,
        request: LLMRequest,
        *,
        user_api_keys: dict[str, str] | None = None,
        user_provider_models: dict[str, str] | None = None,
        preferred_provider: str | None = None,
        local_fallback_enabled: bool | None = None,
    ) -> LLMResponse:
        keys = {
            _normalize_provider(k): v
            for k, v in (user_api_keys or {}).items()
            if k and v
        }
        provider_models = {
            _normalize_provider(k): v.strip()
            for k, v in (user_provider_models or {}).items()
            if k and v and v.strip()
        }
        preferred = (
            _normalize_provider(preferred_provider)
            if preferred_provider and preferred_provider.strip()
            else None
        )
        ordered_adapters = self._build_ordered_adapters(
            user_keys=keys,
            preferred=preferred,
            local_fallback_enabled=local_fallback_enabled,
        )

        errors: list[ProviderError] = []
        fallback_attempts = 0
        eligible: list[tuple[LLMProviderAdapter, str | None]] = []
        for adapter in ordered_adapters:
            provider = adapter.provider_name
            apply_override = not preferred or provider == preferred
            byok_key = keys.get(provider) or (request.api_key_override if apply_override else None)
            if not adapter.is_configured(api_key_override=byok_key):
                continue
            if not self._is_provider_available(provider, using_byok=bool(byok_key)):
                logger.info("Skipping LLM provider %s (circuit open or budget exceeded)", provider)
                continue
            eligible.append((adapter, byok_key))

        for index, (adapter, byok_key) in enumerate(eligible):
            provider = adapter.provider_name
            has_backup = index + 1 < len(eligible)
            apply_override = not preferred or provider == preferred
            timeout_cap = (
                request.provider_timeout_seconds
                if request.provider_timeout_seconds is not None
                else self.provider_timeout_seconds
            )
            effective_timeout = request.timeout_seconds
            if provider != "ollama" and timeout_cap is not None:
                effective_timeout = min(request.timeout_seconds, timeout_cap)

            effective_model_override = (
                request.model_override if (apply_override and request.model_override) else None
            ) or provider_models.get(provider)
            provider_request = replace(
                request,
                api_key_override=byok_key,
                model_override=effective_model_override,
                timeout_seconds=effective_timeout,
            )
            attempt = 0
            while True:
                try:
                    response = adapter.generate(provider_request)
                    final_response = replace(
                        response,
                        fallback_attempts=fallback_attempts,
                        used_byok=bool(byok_key),
                    )
                    self._record_success(final_response)
                    if self._on_event:
                        try:
                            self._on_event(
                                {
                                    "event_type": "llm_generation",
                                    "provider": final_response.provider,
                                    "model": final_response.model,
                                    "status": "success",
                                    "latency_ms": final_response.latency_ms,
                                    "prompt_tokens": final_response.usage.prompt_tokens,
                                    "completion_tokens": final_response.usage.completion_tokens,
                                    "total_tokens": final_response.usage.total_tokens,
                                    "used_byok": final_response.used_byok,
                                    "fallback_attempts": final_response.fallback_attempts,
                                }
                            )
                        except Exception:
                            pass
                    return final_response
                except ProviderError as exc:
                    if isinstance(exc, InvalidRequestError) and not has_backup:
                        self._record_failure(provider, exc, using_byok=bool(byok_key))
                        raise AppError(
                            f"Invalid LLM generation request: {exc.message}",
                            status_code=422,
                            code="generation_invalid_request",
                        ) from exc

                    # Only sleep and retry the same failing endpoint when no backup provider remains.
                    if exc.retryable and not has_backup and attempt < self.max_transient_retries:
                        delay = self.retry_backoff_seconds * (2**attempt)
                        if delay > 0:
                            sleep(delay)
                        attempt += 1
                        continue

                    self._record_failure(provider, exc, using_byok=bool(byok_key))
                    errors.append(exc)
                    fallback_attempts += 1
                    logger.warning(
                        "LLM provider %s failed (%s); cascading to next provider",
                        provider,
                        exc.message,
                    )
                    if self._on_event:
                        try:
                            self._on_event(
                                {
                                    "event_type": "llm_generation",
                                    "provider": provider,
                                    "model": getattr(adapter, "default_model", None),
                                    "status": "error",
                                    "error_code": exc.__class__.__name__,
                                    "used_byok": bool(byok_key),
                                }
                            )
                        except Exception:
                            pass
                    break

        if errors:
            summary = "; ".join(f"{e.provider}: {e.message}" for e in errors)
            raise AppError(
                f"All configured LLM providers failed ({summary})",
                status_code=503,
                code="generation_unavailable",
            )
        raise AppError(
            "No LLM providers are configured or available",
            status_code=503,
            code="generation_unavailable",
        )


def build_router_for_settings(
    settings: Settings,
    *,
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> CentralizedLLMRouter:
    catalog: dict[str, LLMProviderAdapter] = {
        "cerebras": CerebrasProviderAdapter(
            api_key=settings.cerebras_api_key,
            default_model=settings.cerebras_model_name,
        ),
        "gemini": GeminiProviderAdapter(
            api_key=settings.gemini_api_key,
            default_model=settings.gemini_model_name,
            fallback_model=settings.gemini_fallback_model_name,
            base_url=settings.gemini_base_url,
            primary_timeout_seconds=settings.gemini_primary_timeout_seconds,
            fallback_cooldown_seconds=settings.gemini_fallback_cooldown_seconds,
        ),
        "mistral": MistralProviderAdapter(
            api_key=settings.mistral_api_key,
            default_model=settings.mistral_model_name,
            base_url=settings.mistral_base_url,
        ),
        "openrouter": OpenRouterProviderAdapter(
            api_key=settings.openrouter_api_key,
            default_model=settings.openrouter_model_name,
            base_url=settings.openrouter_base_url,
        ),
        "groq": GroqProviderAdapter(
            api_key=settings.groq_api_key,
            default_model=settings.groq_llm_model_name,
            base_url=settings.groq_base_url,
        ),
        "openai": OpenAIProviderAdapter(
            api_key=settings.openai_api_key,
            default_model=settings.openai_model_name,
            base_url=settings.openai_base_url,
        ),
        "claude": ClaudeProviderAdapter(
            api_key=settings.claude_api_key,
            default_model=settings.claude_model_name,
            base_url=settings.claude_base_url,
        ),
        "grok": GrokProviderAdapter(
            api_key=settings.grok_api_key,
            default_model=settings.grok_model_name,
            base_url=settings.grok_base_url,
        ),
        "ollama": OllamaProviderAdapter(
            base_url=settings.ollama_base_url,
            default_model=settings.generation_model_name,
        ),
    }
    raw_providers = settings.llm_router_providers
    if isinstance(raw_providers, str):
        order = [item.strip().lower() for item in raw_providers.split(",") if item.strip()]
    else:
        order = [str(item).strip().lower() for item in raw_providers if str(item).strip()]
    adapters = [catalog[name] for name in order if name in catalog]
    if not adapters:
        adapters = [
            catalog["gemini"],
            catalog["openrouter"],
            catalog["cerebras"],
            catalog["mistral"],
        ]
    return CentralizedLLMRouter(
        adapters,
        catalog=catalog,
        failure_threshold=settings.llm_circuit_breaker_threshold,
        cooldown_seconds=settings.llm_circuit_breaker_cooldown_seconds,
        retry_backoff_seconds=settings.generation_retry_backoff_seconds,
        daily_token_budget=settings.llm_daily_token_quota_per_provider,
        provider_timeout_seconds=settings.llm_provider_timeout_seconds,
        on_event=on_event,
    )


_ROUTER_CACHE_LOCK = RLock()
_ROUTER_CACHE_MAXSIZE = 16
_ROUTER_CACHE: OrderedDict[tuple[object, ...], CentralizedLLMRouter] = OrderedDict()


def _router_cache_key(settings: Settings) -> tuple[object, ...]:
    raw_providers = settings.llm_router_providers
    order = (
        tuple(item.strip().lower() for item in raw_providers.split(",") if item.strip())
        if isinstance(raw_providers, str)
        else tuple(str(item).strip().lower() for item in raw_providers if str(item).strip())
    )
    return (
        order,
        settings.cerebras_api_key,
        settings.cerebras_model_name,
        settings.cerebras_base_url,
        settings.gemini_api_key,
        settings.gemini_model_name,
        settings.gemini_fallback_model_name,
        settings.gemini_base_url,
        settings.gemini_primary_timeout_seconds,
        settings.gemini_fallback_cooldown_seconds,
        settings.mistral_api_key,
        settings.mistral_model_name,
        settings.mistral_base_url,
        settings.openrouter_api_key,
        settings.openrouter_model_name,
        settings.openrouter_base_url,
        settings.groq_api_key,
        settings.groq_llm_model_name,
        settings.groq_base_url,
        settings.openai_api_key,
        settings.openai_model_name,
        settings.openai_base_url,
        settings.claude_api_key,
        settings.claude_model_name,
        settings.claude_base_url,
        settings.grok_api_key,
        settings.grok_model_name,
        settings.grok_base_url,
        settings.ollama_base_url,
        settings.generation_model_name,
        settings.llm_circuit_breaker_threshold,
        settings.llm_circuit_breaker_cooldown_seconds,
        settings.generation_retry_backoff_seconds,
        settings.llm_daily_token_quota_per_provider,
        settings.llm_provider_timeout_seconds,
    )


def get_cached_router_for_settings(settings: Settings) -> CentralizedLLMRouter:
    """Return a bounded LRU-cached router so circuit breakers and latency stats persist."""
    key = _router_cache_key(settings)
    with _ROUTER_CACHE_LOCK:
        router = _ROUTER_CACHE.get(key)
        if router is not None:
            _ROUTER_CACHE.move_to_end(key)
            return router
        router = build_router_for_settings(settings)
        _ROUTER_CACHE[key] = router
        maxsize = max(1, _ROUTER_CACHE_MAXSIZE)
        while len(_ROUTER_CACHE) > maxsize:
            _ROUTER_CACHE.popitem(last=False)
        return router

