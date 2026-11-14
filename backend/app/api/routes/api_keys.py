"""BYOK (Bring Your Own Key) API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.providers.ollama import probe_ollama_models
from app.schemas.base import ApiSchema
from app.services.auth import api_keys as api_key_service
from app.services.observability.usage import get_user_model_usage_and_quota

router = APIRouter(prefix="/auth/api-keys", tags=["byok"])
DatabaseSession = Annotated[Session, Depends(get_db)]

_PROVIDER_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    ("gemini", "Gemini", "gemini_api_key", "gemini_model_name"),
    ("groq", "Groq", "groq_api_key", "groq_llm_model_name"),
    ("openai", "OpenAI", "openai_api_key", "openai_model_name"),
    ("claude", "Claude", "claude_api_key", "claude_model_name"),
    ("grok", "Grok", "grok_api_key", "grok_model_name"),
    ("openrouter", "OpenRouter", "openrouter_api_key", "openrouter_model_name"),
    ("cerebras", "Cerebras", "cerebras_api_key", "cerebras_model_name"),
    ("mistral", "Mistral", "mistral_api_key", "mistral_model_name"),
)


class APIKeyUpsertRequest(ApiSchema):
    api_key: str = Field(min_length=8, max_length=512)
    model_name: str | None = Field(default=None, max_length=128)


class APIKeyMetadataResponse(ApiSchema):
    id: UUID
    provider: str
    key_hint: str
    is_active: bool
    usage_requests: int
    usage_tokens: int
    last_used_at: datetime | None = None
    created_at: datetime


class APIKeyListResponse(ApiSchema):
    items: list[APIKeyMetadataResponse]


class ProviderStatusItem(ApiSchema):
    id: str
    label: str
    configured_server: bool
    configured_byok: bool
    configured: bool
    key_hint: str | None = None
    default_model: str
    selected_model: str | None = None
    suggested_models: list[str] = Field(default_factory=list)
    is_local: bool = False
    available: bool = True


class LocalModelStatus(ApiSchema):
    provider: str = "ollama"
    available: bool
    connected: bool
    base_url: str
    configured_model: str
    active_model: str | None = None
    installed_models: list[str]


class ModelUsageBreakdownItem(ApiSchema):
    provider: str
    model_name: str
    requests_today: int
    tokens_today: int
    total_requests: int
    total_tokens: int
    estimated_cost_usd: float
    last_used_at: datetime | None = None


class ModelUsageQuotaResponse(ApiSchema):
    enrolled_users: int
    shared_requests_used_today: int
    user_daily_request_cap: int
    user_requests_remaining_today: int
    system_pool_total: int
    system_pool_used_today: int
    system_pool_remaining: int
    byok_requests_today: int
    local_requests_today: int
    total_requests_today: int
    total_tokens_today: int
    total_requests_all_time: int
    total_tokens_all_time: int
    resets_at: datetime
    models: list[ModelUsageBreakdownItem] = Field(default_factory=list)


class ModelsStatusResponse(ApiSchema):
    local: LocalModelStatus
    providers: list[ProviderStatusItem]
    router_order: list[str]
    usage: ModelUsageQuotaResponse | None = None


class LocalFallbackToggleRequest(ApiSchema):
    connected: bool


class ProviderModelSelectRequest(ApiSchema):
    provider: str = Field(min_length=1, max_length=64)
    model_name: str | None = Field(default=None, max_length=128)


class ProviderModelSelectResponse(ApiSchema):
    provider: str
    selected_model: str | None = None


def _dedupe_models(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


@router.get("", response_model=APIKeyListResponse)
def list_api_keys(
    session: DatabaseSession,
    user: CurrentUser,
) -> APIKeyListResponse:
    items = api_key_service.list_user_api_keys(session, user.id)
    return APIKeyListResponse(items=items)


@router.get("/models-status", response_model=ModelsStatusResponse)
def get_models_status(
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> ModelsStatusResponse:
    settings = request.app.state.settings
    byok_records = {
        rec.provider: rec for rec in api_key_service.list_user_api_keys(session, user.id)
    }
    local_available, installed_models, active_model = probe_ollama_models(
        settings.ollama_base_url,
        settings.generation_model_name,
        timeout_seconds=1.5,
    )
    local_connected = (
        api_key_service.get_local_fallback_enabled(session, user.id, default=local_available)
        if local_available
        else False
    )

    user_models = api_key_service.get_user_provider_models(session, user.id)
    providers: list[ProviderStatusItem] = []
    for provider_id, label, key_attr, model_attr in _PROVIDER_CATALOG:
        server_configured = bool(getattr(settings, key_attr, None))
        byok_rec = byok_records.get(provider_id)
        byok_configured = byok_rec is not None
        configured_default = str(getattr(settings, model_attr, ""))
        selected_model = user_models.get(provider_id)
        suggested_models = _dedupe_models(
            [
                *([selected_model] if selected_model else []),
                configured_default,
                *api_key_service.SUGGESTED_PROVIDER_MODELS.get(provider_id, []),
            ]
        )
        providers.append(
            ProviderStatusItem(
                id=provider_id,
                label=label,
                configured_server=server_configured,
                configured_byok=byok_configured,
                configured=server_configured or byok_configured,
                key_hint=byok_rec.key_hint if byok_rec is not None else None,
                default_model=selected_model or configured_default,
                selected_model=selected_model,
                suggested_models=suggested_models,
                is_local=False,
                available=True,
            )
        )

    ollama_selected = user_models.get("ollama")
    ollama_default = ollama_selected or active_model or settings.generation_model_name
    ollama_suggestions = _dedupe_models(
        [
            *([ollama_selected] if ollama_selected else []),
            *installed_models,
            ollama_default,
            *api_key_service.SUGGESTED_PROVIDER_MODELS.get("ollama", []),
        ]
    )
    providers.append(
        ProviderStatusItem(
            id="ollama",
            label="Local Ollama",
            configured_server=local_available,
            configured_byok=False,
            configured=local_available,
            key_hint=None,
            default_model=ollama_default,
            selected_model=ollama_selected,
            suggested_models=ollama_suggestions,
            is_local=True,
            available=local_available,
        )
    )

    raw_order = settings.llm_router_providers
    router_order = (
        [item.strip().lower() for item in raw_order.split(",") if item.strip()]
        if isinstance(raw_order, str)
        else [str(item).strip().lower() for item in raw_order if str(item).strip()]
    )

    usage_snapshot = get_user_model_usage_and_quota(session, user.id, settings)

    return ModelsStatusResponse(
        local=LocalModelStatus(
            available=local_available,
            connected=local_connected,
            base_url=settings.ollama_base_url,
            configured_model=settings.generation_model_name,
            active_model=active_model,
            installed_models=installed_models,
        ),
        providers=providers,
        router_order=router_order,
        usage=ModelUsageQuotaResponse(**usage_snapshot),
    )


@router.get("/usage", response_model=ModelUsageQuotaResponse)
def get_model_usage_quota(
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> ModelUsageQuotaResponse:
    """Return this user's model usage breakdown and dynamic daily quota."""
    settings = request.app.state.settings
    return ModelUsageQuotaResponse(**get_user_model_usage_and_quota(session, user.id, settings))


@router.post("/local-fallback", response_model=LocalModelStatus)
def set_local_fallback(
    payload: LocalFallbackToggleRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> LocalModelStatus:
    settings = request.app.state.settings
    local_available, installed_models, active_model = probe_ollama_models(
        settings.ollama_base_url,
        settings.generation_model_name,
        timeout_seconds=1.5,
    )
    pref = api_key_service.set_local_fallback_enabled(session, user.id, payload.connected)
    return LocalModelStatus(
        available=local_available,
        connected=bool(local_available and pref),
        base_url=settings.ollama_base_url,
        configured_model=settings.generation_model_name,
        active_model=active_model,
        installed_models=installed_models,
    )


@router.post("/provider-model", response_model=ProviderModelSelectResponse)
def set_provider_model(
    payload: ProviderModelSelectRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ProviderModelSelectResponse:
    norm_provider = api_key_service.normalize_provider_name(payload.provider)
    selected = api_key_service.set_user_provider_model(
        session,
        user.id,
        norm_provider,
        payload.model_name,
    )
    return ProviderModelSelectResponse(provider=norm_provider, selected_model=selected)


@router.put("/{provider}", response_model=APIKeyMetadataResponse)
def save_api_key(
    provider: str,
    payload: APIKeyUpsertRequest,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> APIKeyMetadataResponse:
    return api_key_service.save_user_api_key(
        session,
        user.id,
        provider,
        payload.api_key,
        request.app.state.settings,
        model_name=payload.model_name,
    )


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    provider: str,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    api_key_service.revoke_user_api_key(session, user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
