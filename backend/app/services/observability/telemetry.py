"""Observability and Langfuse-compatible telemetry without logging secrets or private content."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.telemetry import TelemetryEvent

logger = logging.getLogger(__name__)

# Approximate per-1M-token pricing in USD for cost estimation
PROVIDER_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "cerebras": (0.0, 0.0),      # $5 30-day starter promo (gpt-oss-120b paid: $0.35/$0.75)
    "gemini": (0.0, 0.0),        # Gemini 3.8 Flash Free tier ($0.75/$3.75 on paid tier)
    "mistral": (0.10, 0.30),     # Mistral paid API (payment activation required)
    "openrouter": (0.0, 0.0),    # Free router (:free / openrouter/free, 50 RPD free)
    "ollama": (0.0, 0.0),        # Local self-hosted
    "cloudflare": (0.0, 0.0),    # Workers AI 10,000 Neurons/day free allowance
    "jina": (0.0, 0.0),          # r.jina.ai keyless free Reader (10M rerank is non-commercial)
    "groq": (0.04, 0.04),        # Groq Whisper Large V3 Turbo tariff ($0.04/hr after free tier)
}

FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
        "prompt",
        "raw_text",
        "document_text",
        "encrypted_key",
    }
)


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
    return cleaned


def estimate_cost_usd(
    provider: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    if not provider:
        return 0.0
    in_rate, out_rate = PROVIDER_PRICING_PER_1M.get(provider.lower(), (0.0, 0.0))
    cost = (max(0, prompt_tokens) * in_rate + max(0, completion_tokens) * out_rate) / 1_000_000.0
    return round(cost, 8)


def record_telemetry_event(
    session: Session,
    *,
    event_type: str,
    operation: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    status: str = "success",
    latency_ms: float | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost_usd: float | None = None,
    error_code: str | None = None,
    user_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
    commit: bool = True,
) -> TelemetryEvent:
    cost = (
        estimated_cost_usd
        if estimated_cost_usd is not None
        else estimate_cost_usd(provider, prompt_tokens, completion_tokens)
    )
    safe_meta = sanitize_metadata(metadata)
    is_success = status.lower() == "success"
    event = TelemetryEvent(
        user_id=user_id,
        category=event_type,
        operation=operation or event_type,
        provider=provider,
        model_name=model,
        success=is_success,
        duration_ms=latency_ms,
        input_tokens=max(0, prompt_tokens),
        output_tokens=max(0, completion_tokens),
        estimated_cost_usd=cost,
        error_code=error_code,
        details=safe_meta,
    )
    session.add(event)
    if commit:
        session.commit()
        session.refresh(event)
    else:
        session.flush()

    if settings and settings.langfuse_enabled and settings.langfuse_public_key and settings.langfuse_secret_key:
        _export_to_langfuse(event, settings)

    return event


def _export_to_langfuse(event: TelemetryEvent, settings: Settings) -> None:
    url = f"{settings.langfuse_host.rstrip('/')}/api/public/ingestion"
    in_tokens = int(event.input_tokens or 0)
    out_tokens = int(event.output_tokens or 0)
    payload = {
        "batch": [
            {
                "id": str(uuid4()),
                "type": "generation-create",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "body": {
                    "id": str(event.id),
                    "name": event.category,
                    "model": event.model_name or event.provider or "unknown",
                    "usage": {
                        "input": in_tokens,
                        "output": out_tokens,
                        "total": in_tokens + out_tokens,
                    },
                    "level": "ERROR" if not event.success else "DEFAULT",
                    "statusMessage": event.error_code,
                    "metadata": event.details or {},
                },
            }
        ]
    }
    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(
                url,
                auth=(settings.langfuse_public_key or "", settings.langfuse_secret_key or ""),
                json=payload,
            )
    except Exception as exc:
        logger.debug("Langfuse export skipped: %s", exc)


def summarize_telemetry(
    session: Session,
    *,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    filters = []
    if user_id is not None:
        filters.append(TelemetryEvent.user_id == user_id)

    events = list(
        session.scalars(
            select(TelemetryEvent).where(*filters).order_by(TelemetryEvent.created_at.desc())
        ).all()
    )
    total_events = len(events)
    if total_events == 0:
        return {
            "total_events": 0,
            "error_count": 0,
            "total_tokens": 0,
            "total_estimated_cost_usd": 0.0,
            "avg_latency_ms": 0.0,
            "by_provider": {},
            "by_event_type": {},
        }

    error_count = sum(1 for e in events if not e.success)
    total_tokens = sum(int(e.input_tokens or 0) + int(e.output_tokens or 0) for e in events)
    total_cost = round(sum(float(e.estimated_cost_usd or 0.0) for e in events), 8)
    latencies = [float(e.duration_ms) for e in events if e.duration_ms is not None]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    by_provider: dict[str, dict[str, Any]] = {}
    by_event_type: dict[str, int] = {}
    for e in events:
        by_event_type[e.category] = by_event_type.get(e.category, 0) + 1
        prov = e.provider or "internal"
        bucket = by_provider.setdefault(
            prov,
            {"requests": 0, "errors": 0, "tokens": 0, "estimated_cost_usd": 0.0},
        )
        bucket["requests"] += 1
        if not e.success:
            bucket["errors"] += 1
        bucket["tokens"] += int(e.input_tokens or 0) + int(e.output_tokens or 0)
        bucket["estimated_cost_usd"] = round(
            bucket["estimated_cost_usd"] + float(e.estimated_cost_usd or 0.0), 8
        )

    return {
        "total_events": total_events,
        "error_count": error_count,
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": total_cost,
        "avg_latency_ms": avg_latency,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
    }
