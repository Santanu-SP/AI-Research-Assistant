"""Encrypted Bring-Your-Own-Key (BYOK) management per user."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.api_key import UserAPIKey

SUPPORTED_BYOK_PROVIDERS = frozenset(
    {"cerebras", "gemini", "mistral", "openrouter", "groq", "jina", "cloudflare"}
)


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
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_BYOK_PROVIDERS:
        raise AppError(
            f"Unsupported provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_BYOK_PROVIDERS))}",
            status_code=422,
            code="unsupported_byok_provider",
        )
    cleaned_key = raw_key.strip()
    if len(cleaned_key) < 8 or len(cleaned_key) > 512 or any(ch.isspace() for ch in cleaned_key):
        raise AppError(
            "Invalid API key format",
            status_code=422,
            code="invalid_byok_key",
        )
    return normalized_provider, cleaned_key


def save_user_api_key(
    session: Session,
    user_id: UUID,
    provider: str,
    raw_key: str,
    settings: Settings,
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
    norm_provider = provider.strip().lower()
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

