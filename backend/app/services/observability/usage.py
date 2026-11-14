"""Per-user model usage aggregation and dynamic fair-share daily quota enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.models.telemetry import TelemetryEvent
from app.models.user import User

_SERVER_PROVIDER_KEY_ATTRS: tuple[tuple[str, str], ...] = (
    ("gemini", "gemini_api_key"),
    ("groq", "groq_api_key"),
    ("openai", "openai_api_key"),
    ("claude", "claude_api_key"),
    ("grok", "grok_api_key"),
    ("openrouter", "openrouter_api_key"),
    ("cerebras", "cerebras_api_key"),
    ("mistral", "mistral_api_key"),
)


def utc_day_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the current UTC day [start, next_reset) timestamps."""

    current = now or utc_now()
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def is_local_event(event: TelemetryEvent) -> bool:
    details = event.details or {}
    return (event.provider or "").strip().lower() == "ollama" or details.get("is_local") is True


def is_byok_event(event: TelemetryEvent) -> bool:
    details = event.details or {}
    return details.get("used_byok") is True


def is_shared_server_event(event: TelemetryEvent) -> bool:
    """True when an event consumed the shared server-side cloud AI API pool."""

    if not event.success:
        return False
    return not is_local_event(event) and not is_byok_event(event)


def _configured_server_providers(settings: Settings) -> list[str]:
    return [
        provider_id
        for provider_id, attr in _SERVER_PROVIDER_KEY_ATTRS
        if bool(getattr(settings, attr, None))
    ]


def _all_server_providers_token_exhausted(settings: Settings, configured: list[str]) -> bool:
    if not configured or settings.generation_runtime.strip().lower() != "router":
        return False
    from app.providers.router import get_cached_router_for_settings

    snapshot = get_cached_router_for_settings(settings).get_health_snapshot()
    if not snapshot:
        return False
    tracked = [snapshot[name] for name in configured if name in snapshot]
    if not tracked:
        return False
    return all(
        int(item.get("tokens_used_today") or 0) >= int(item.get("daily_token_budget") or 1)
        for item in tracked
    )


def get_user_model_usage_and_quota(
    session: Session,
    user_id: UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Compute a user's model usage and fair-share daily cap.

    The per-user daily shared request cap scales dynamically with both:
    - active enrolled users (`max(1, count)`), dividing the daily pool fairly
    - remaining shared AI API requests left globally today across all users.
    BYOK and Local Ollama requests are tracked in usage totals without counting
    against the shared server API quota.
    """

    today_start, resets_at = utc_day_window()
    enrolled_users = max(
        1,
        int(session.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 1),
    )

    configured = _configured_server_providers(settings)
    if settings.llm_daily_system_request_pool is not None:
        system_pool_total = settings.llm_daily_system_request_pool
    else:
        system_pool_total = max(1, len(configured)) * settings.llm_daily_requests_per_provider

    today_events = list(
        session.scalars(
            select(TelemetryEvent).where(
                TelemetryEvent.category == "llm_generation",
                TelemetryEvent.created_at >= today_start,
            )
        ).all()
    )
    system_pool_used_today = sum(1 for evt in today_events if is_shared_server_event(evt))
    if _all_server_providers_token_exhausted(settings, configured):
        system_pool_remaining = 0
    else:
        system_pool_remaining = max(0, system_pool_total - system_pool_used_today)

    user_events = list(
        session.scalars(
            select(TelemetryEvent)
            .where(
                TelemetryEvent.category == "llm_generation",
                TelemetryEvent.user_id == user_id,
                TelemetryEvent.success.is_(True),
            )
            .order_by(TelemetryEvent.created_at.desc())
        ).all()
    )

    shared_requests_used_today = 0
    byok_requests_today = 0
    local_requests_today = 0
    total_tokens_today = 0
    total_requests_all_time = 0
    total_tokens_all_time = 0

    model_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for evt in user_events:
        is_today = evt.created_at >= today_start
        tokens = int(evt.input_tokens or 0) + int(evt.output_tokens or 0)
        total_requests_all_time += 1
        total_tokens_all_time += tokens

        if is_today:
            total_tokens_today += tokens
            if is_byok_event(evt):
                byok_requests_today += 1
            elif is_local_event(evt):
                local_requests_today += 1
            else:
                shared_requests_used_today += 1

        provider_key = (evt.provider or "unknown").strip().lower()
        model_key = (evt.model_name or evt.provider or "default").strip()
        bucket = model_buckets.setdefault(
            (provider_key, model_key),
            {
                "provider": provider_key,
                "model_name": model_key,
                "requests_today": 0,
                "tokens_today": 0,
                "total_requests": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "last_used_at": evt.created_at,
            },
        )
        bucket["total_requests"] += 1
        bucket["total_tokens"] += tokens
        bucket["estimated_cost_usd"] = round(
            float(bucket["estimated_cost_usd"]) + float(evt.estimated_cost_usd or 0.0),
            8,
        )
        if evt.created_at > bucket["last_used_at"]:
            bucket["last_used_at"] = evt.created_at
        if is_today:
            bucket["requests_today"] += 1
            bucket["tokens_today"] += tokens

    per_user_fair_share = max(1, system_pool_total // enrolled_users)
    user_requests_remaining_today = min(
        max(0, per_user_fair_share - shared_requests_used_today),
        system_pool_remaining,
    )
    user_daily_request_cap = min(
        per_user_fair_share,
        shared_requests_used_today + system_pool_remaining,
    )

    models_breakdown = sorted(
        model_buckets.values(),
        key=lambda item: (
            -int(item["requests_today"]),
            -int(item["total_requests"]),
            item["provider"],
            item["model_name"],
        ),
    )

    return {
        "enrolled_users": enrolled_users,
        "shared_requests_used_today": shared_requests_used_today,
        "user_daily_request_cap": user_daily_request_cap,
        "user_requests_remaining_today": user_requests_remaining_today,
        "system_pool_total": system_pool_total,
        "system_pool_used_today": system_pool_used_today,
        "system_pool_remaining": system_pool_remaining,
        "byok_requests_today": byok_requests_today,
        "local_requests_today": local_requests_today,
        "total_requests_today": shared_requests_used_today + byok_requests_today + local_requests_today,
        "total_tokens_today": total_tokens_today,
        "total_requests_all_time": total_requests_all_time,
        "total_tokens_all_time": total_tokens_all_time,
        "resets_at": resets_at,
        "models": models_breakdown,
    }


def enforce_user_daily_model_quota(
    session: Session,
    user_id: UUID,
    settings: Settings,
    *,
    preferred_provider: str | None = None,
) -> None:
    """Reject shared-pool requests when user or global daily API quota is exhausted.

    Requests explicitly routed to Local Ollama or a provider where the user has an
    active BYOK key bypass the shared pool cap since they carry independent quota.
    """

    from app.services.auth import api_keys as api_key_service

    pref = (
        api_key_service.normalize_provider_name(preferred_provider)
        if preferred_provider and preferred_provider.strip()
        else None
    )
    if pref == "ollama":
        return
    if pref is not None:
        user_byok = {
            rec.provider for rec in api_key_service.list_user_api_keys(session, user_id)
        }
        if pref in user_byok:
            return

    quota = get_user_model_usage_and_quota(session, user_id, settings)
    if quota["user_requests_remaining_today"] <= 0:
        enrolled = quota["enrolled_users"]
        raise AppError(
            (
                f"Daily shared AI request cap reached "
                f"({quota['shared_requests_used_today']}/{quota['user_daily_request_cap']} used today "
                f"across {enrolled} enrolled user{'s' if enrolled != 1 else ''}; "
                f"{quota['system_pool_remaining']} shared API requests left today). "
                "Add your own key via 'Apply my API key', switch to Local Ollama, or wait until tomorrow (UTC)."
            ),
            status_code=429,
            code="daily_model_quota_exceeded",
        )
