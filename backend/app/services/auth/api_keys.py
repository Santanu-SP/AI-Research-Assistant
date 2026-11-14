"""Encrypted Bring-Your-Own-Key (BYOK) management per user."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from threading import RLock
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.api_key import UserAPIKey

SUPPORTED_BYOK_PROVIDERS = frozenset(
    {
        "cerebras",
        "gemini",
        "mistral",
        "openrouter",
        "groq",
        "openai",
        "claude",
        "grok",
        "jina",
        "cloudflare",
    }
)
PROVIDER_ALIASES: dict[str, str] = {
    "anthropic": "claude",
    "xai": "grok",
}

SUGGESTED_PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.1-flash-lite",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "o3-mini",
    ],
    "claude": [
        "claude-3-5-haiku-latest",
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet-latest",
    ],
    "grok": [
        "grok-3-mini-fast",
        "grok-3-mini",
        "grok-3",
    ],
    "openrouter": [
        "openrouter/free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.5-flash",
    ],
    "cerebras": [
        "gpt-oss-120b",
        "llama-3.3-70b",
        "llama3.1-8b",
    ],
    "mistral": [
        "mistral-small-4",
        "mistral-small-latest",
        "mistral-large-latest",
    ],
    "ollama": [
        "qwen3.5:9b",
        "llama3.2:3b",
        "qwen2.5:3b",
    ],
}


def normalize_provider_name(provider: str) -> str:
    cleaned = provider.strip().lower()
    return PROVIDER_ALIASES.get(cleaned, cleaned)


def detect_provider_from_key(raw_key: str) -> str | None:
    cleaned = raw_key.strip()
    if cleaned.startswith("AIza"):
        return "gemini"
    if cleaned.startswith("gsk_"):
        return "groq"
    if cleaned.startswith("sk-ant-"):
        return "claude"
    if cleaned.startswith("sk-or-"):
        return "openrouter"
    if cleaned.startswith("xai-"):
        return "grok"
    if cleaned.startswith("csk-"):
        return "cerebras"
    if cleaned.startswith("sk-"):
        return "openai"
    return None


def _fernet_for_settings(settings: Settings) -> Fernet:
    raw_secret = (settings.api_key_encryption_secret or "").strip()
    if not raw_secret:
        raw_secret = "dev-only-byok-encryption-secret-change-in-production"
    secret = raw_secret.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def mask_api_key(raw_key: str) -> str:
    cleaned = raw_key.strip()
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def validate_provider_and_key(provider: str, raw_key: str) -> tuple[str, str]:
    cleaned_key = raw_key.strip()
    if len(cleaned_key) < 8 or len(cleaned_key) > 512 or any(ch.isspace() for ch in cleaned_key):
        raise AppError(
            "Invalid API key format",
            status_code=422,
            code="invalid_byok_key",
        )
    normalized_provider = normalize_provider_name(provider)
    if normalized_provider in {"", "auto", "detect"}:
        detected = detect_provider_from_key(cleaned_key)
        if not detected:
            raise AppError(
                "Could not detect provider from this API key format; please choose a provider explicitly.",
                status_code=422,
                code="undetectable_byok_provider",
            )
        normalized_provider = detected
    if normalized_provider not in SUPPORTED_BYOK_PROVIDERS:
        raise AppError(
            f"Unsupported provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_BYOK_PROVIDERS))}",
            status_code=422,
            code="unsupported_byok_provider",
        )
    return normalized_provider, cleaned_key


def save_user_api_key(
    session: Session,
    user_id: UUID,
    provider: str,
    raw_key: str,
    settings: Settings,
    *,
    model_name: str | None = None,
) -> UserAPIKey:
    norm_provider, cleaned_key = validate_provider_and_key(provider, raw_key)
    fernet = _fernet_for_settings(settings)
    encrypted = fernet.encrypt(cleaned_key.encode("utf-8")).decode("ascii")
    hint = mask_api_key(cleaned_key)

    existing = session.scalar(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == norm_provider,
        )
    )
    if existing is not None:
        existing.encrypted_key = encrypted
        existing.key_hint = hint
        existing.is_active = True
        existing.revoked_at = None
        session.add(existing)
        session.commit()
        session.refresh(existing)
        if model_name is not None:
            set_user_provider_model(user_id, norm_provider, model_name)
        return existing

    record = UserAPIKey(
        user_id=user_id,
        provider=norm_provider,
        encrypted_key=encrypted,
        key_hint=hint,
        is_active=True,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    if model_name is not None:
        set_user_provider_model(user_id, norm_provider, model_name)
    return record


def list_user_api_keys(session: Session, user_id: UUID) -> list[UserAPIKey]:
    return list(
        session.scalars(
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user_id, UserAPIKey.is_active.is_(True))
            .order_by(UserAPIKey.provider)
        ).all()
    )


def revoke_user_api_key(
    session: Session,
    user_id: UUID,
    provider: str,
) -> bool:
    norm_provider = normalize_provider_name(provider)
    record = session.scalar(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == norm_provider,
            UserAPIKey.is_active.is_(True),
        )
    )
    if record is None:
        raise AppError(
            "API key not found for provider",
            status_code=404,
            code="byok_key_not_found",
        )
    record.is_active = False
    record.revoked_at = datetime.now(timezone.utc)
    record.encrypted_key = ""
    session.add(record)
    session.commit()
    set_user_provider_model(user_id, norm_provider, None)
    return True


def get_decrypted_user_api_keys(
    session: Session,
    user_id: UUID,
    settings: Settings,
) -> dict[str, str]:
    fernet = _fernet_for_settings(settings)
    records = list_user_api_keys(session, user_id)
    decrypted: dict[str, str] = {}
    for record in records:
        if not record.encrypted_key:
            continue
        try:
            raw = fernet.decrypt(record.encrypted_key.encode("ascii")).decode("utf-8")
            decrypted[record.provider] = raw
        except InvalidToken:
            continue
    return decrypted


def record_key_usage(
    session: Session,
    user_id: UUID,
    provider: str,
    tokens: int = 0,
) -> None:
    record = session.scalar(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider.strip().lower(),
            UserAPIKey.is_active.is_(True),
        )
    )
    if record is None:
        return
    record.usage_requests = int(record.usage_requests or 0) + 1
    record.usage_tokens = int(record.usage_tokens or 0) + max(0, int(tokens))
    record.last_used_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()


_LOCAL_FALLBACK_PREF_LOCK = RLock()
_USER_LOCAL_FALLBACK_PREF: dict[UUID, bool] = {}
_USER_PROVIDER_MODELS: dict[tuple[UUID, str], str] = {}


def set_user_provider_model(
    user_id: UUID,
    provider: str,
    model_name: str | None,
) -> str | None:
    """Persist or clear user's selected/custom model override for a provider."""
    norm_provider = normalize_provider_name(provider)
    if norm_provider not in SUPPORTED_BYOK_PROVIDERS and norm_provider != "ollama":
        raise AppError(
            f"Unsupported provider '{provider}'",
            status_code=422,
            code="unsupported_byok_provider",
        )
    cleaned = model_name.strip() if model_name else ""
    with _LOCAL_FALLBACK_PREF_LOCK:
        if not cleaned:
            _USER_PROVIDER_MODELS.pop((user_id, norm_provider), None)
            return None
        _USER_PROVIDER_MODELS[(user_id, norm_provider)] = cleaned
        return cleaned


def get_user_provider_models(user_id: UUID) -> dict[str, str]:
    """Return all user-configured provider -> custom/selected model overrides."""
    with _LOCAL_FALLBACK_PREF_LOCK:
        return {
            prov: model
            for (uid, prov), model in _USER_PROVIDER_MODELS.items()
            if uid == user_id
        }


def get_local_fallback_pref(user_id: UUID) -> bool | None:
    """Return explicit user local fallback preference if set, else None."""
    with _LOCAL_FALLBACK_PREF_LOCK:
        return _USER_LOCAL_FALLBACK_PREF.get(user_id)


def get_local_fallback_enabled(user_id: UUID, *, default: bool = True) -> bool:
    """Return user's local Ollama fallback preference (defaults to `default` until toggled)."""
    with _LOCAL_FALLBACK_PREF_LOCK:
        if user_id in _USER_LOCAL_FALLBACK_PREF:
            return _USER_LOCAL_FALLBACK_PREF[user_id]
        return default


def set_local_fallback_enabled(user_id: UUID, enabled: bool) -> bool:
    """Persist user's local Ollama fallback connect/disconnect state in memory."""
    with _LOCAL_FALLBACK_PREF_LOCK:
        _USER_LOCAL_FALLBACK_PREF[user_id] = bool(enabled)
        return _USER_LOCAL_FALLBACK_PREF[user_id]

