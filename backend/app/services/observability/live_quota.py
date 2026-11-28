"""Live provider API-key balance probing (OpenRouter) and rate-limit resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Literal

import httpx

from app.core.config import Settings
from app.providers.base import (
    get_rate_limit_snapshot,
    get_shared_http_client,
    key_scope_fingerprint,
)

logger = logging.getLogger(__name__)

LiveQuotaSource = Literal["provider_api", "response_headers", "app_tracked"]


@dataclass(frozen=True)
class LiveKeyQuota:
    """Real-time provider quota and balance telemetry resolved for a single key."""

    source: LiveQuotaSource
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens: str | None = None
    credit_usage_usd: float | None = None
    credit_limit_usd: float | None = None
    credit_remaining_usd: float | None = None
    is_free_tier: bool | None = None
    synced_at: datetime | None = None


_OPENROUTER_CACHE_LOCK = Lock()
_OPENROUTER_KEY_CACHE: dict[str, tuple[float, LiveKeyQuota]] = {}


def clear_live_quota_cache() -> None:
    """Clear cached OpenRouter key probe responses (for tests)."""
    with _OPENROUTER_CACHE_LOCK:
        _OPENROUTER_KEY_CACHE.clear()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def probe_openrouter_key(
    api_key: str,
    *,
    base_url: str = "https://openrouter.ai/api/v1",
    timeout_seconds: float = 2.5,
    ttl_seconds: float = 60.0,
    force_refresh: bool = False,
    client: httpx.Client | None = None,
) -> LiveKeyQuota | None:
    """Query OpenRouter's ``/auth/key`` endpoint with a short TTL cache keyed by key hash."""
    cleaned_key = (api_key or "").strip()
    if not cleaned_key:
        return None

    cache_key = f"{base_url.rstrip('/')}:{key_scope_fingerprint(cleaned_key, is_byok=True)}"
    now_ts = _utc_now().timestamp()
    if not force_refresh and ttl_seconds > 0:
        with _OPENROUTER_CACHE_LOCK:
            cached = _OPENROUTER_KEY_CACHE.get(cache_key)
            if cached is not None and (now_ts - cached[0]) <= ttl_seconds:
                return cached[1]

    url = f"{base_url.rstrip('/')}/auth/key"
    headers = {"Authorization": f"Bearer {cleaned_key}"}
    active_client = client if client is not None else get_shared_http_client()
    try:
        response = active_client.get(url, headers=headers, timeout=timeout_seconds)
        if response.status_code >= 400:
            return None
        payload = response.json()
    except Exception as exc:
        logger.debug("OpenRouter key probe failed: %s", exc)
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None

    usage_usd = _as_float(data.get("usage"))
    limit_usd = _as_float(data.get("limit"))
    remaining_usd = _as_float(data.get("limit_remaining"))
    if remaining_usd is None and limit_usd is not None and usage_usd is not None:
        remaining_usd = round(max(0.0, limit_usd - usage_usd), 4)

    raw_free = data.get("is_free_tier")
    is_free_tier = bool(raw_free) if isinstance(raw_free, bool) else None

    rate_limit = data.get("rate_limit") if isinstance(data.get("rate_limit"), dict) else {}
    limit_requests = _as_int(rate_limit.get("requests")) if rate_limit else None
    interval = rate_limit.get("interval") if rate_limit else None
    reset_requests = str(interval).strip() if interval else None

    result = LiveKeyQuota(
        source="provider_api",
        limit_requests=limit_requests,
        reset_requests=reset_requests,
        credit_usage_usd=usage_usd,
        credit_limit_usd=limit_usd,
        credit_remaining_usd=remaining_usd,
        is_free_tier=is_free_tier,
        synced_at=_utc_now(),
    )
    if ttl_seconds > 0:
        with _OPENROUTER_CACHE_LOCK:
            _OPENROUTER_KEY_CACHE[cache_key] = (_utc_now().timestamp(), result)
    return result


def resolve_live_provider_quota(
    provider: str,
    *,
    api_key: str | None,
    is_byok: bool,
    settings: Settings,
    allow_live_probe: bool = False,
    force_refresh: bool = False,
) -> LiveKeyQuota | None:
    """Resolve live key balance and/or latest response rate-limit headers for ``provider``."""
    probed: LiveKeyQuota | None = None
    cleaned_key = (api_key or "").strip() or None
    if provider == "openrouter" and cleaned_key:
        can_network_probe = allow_live_probe and (
            settings.app_environment != "test" or force_refresh
        )
        if can_network_probe:
            probed = probe_openrouter_key(
                cleaned_key,
                base_url=settings.openrouter_base_url,
                force_refresh=force_refresh,
            )
        else:
            cache_key = (
                f"{settings.openrouter_base_url.rstrip('/')}:"
                f"{key_scope_fingerprint(cleaned_key, is_byok=True)}"
            )
            now_ts = _utc_now().timestamp()
            with _OPENROUTER_CACHE_LOCK:
                cached = _OPENROUTER_KEY_CACHE.get(cache_key)
                if cached is not None and (now_ts - cached[0]) <= 300.0:
                    probed = cached[1]

    header_snapshot = get_rate_limit_snapshot(
        provider,
        api_key=cleaned_key,
        is_byok=is_byok,
    )

    if probed is None and header_snapshot is None:
        return None

    if probed is not None:
        if header_snapshot is None:
            return probed
        return LiveKeyQuota(
            source="provider_api",
            limit_requests=header_snapshot.limit_requests or probed.limit_requests,
            remaining_requests=header_snapshot.remaining_requests,
            reset_requests=header_snapshot.reset_requests or probed.reset_requests,
            limit_tokens=header_snapshot.limit_tokens,
            remaining_tokens=header_snapshot.remaining_tokens,
            reset_tokens=header_snapshot.reset_tokens,
            credit_usage_usd=probed.credit_usage_usd,
            credit_limit_usd=probed.credit_limit_usd,
            credit_remaining_usd=probed.credit_remaining_usd,
            is_free_tier=probed.is_free_tier,
            synced_at=max(
                ts for ts in (probed.synced_at, header_snapshot.captured_at) if ts is not None
            ),
        )

    assert header_snapshot is not None
    return LiveKeyQuota(
        source="response_headers",
        limit_requests=header_snapshot.limit_requests,
        remaining_requests=header_snapshot.remaining_requests,
        reset_requests=header_snapshot.reset_requests,
        limit_tokens=header_snapshot.limit_tokens,
        remaining_tokens=header_snapshot.remaining_tokens,
        reset_tokens=header_snapshot.reset_tokens,
        synced_at=header_snapshot.captured_at,
    )
