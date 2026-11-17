"""Fixed dual-window (3-hour & 2-day) per-model AI credits and usage service."""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from time import sleep
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.api_key import UserAPIKey, UserModelPreference
from app.models.research import Research
from app.models.usage import DailyQuotaUsage, ModelUsageDaily
from app.models.user import AuthSession, User


GLOBAL_QUOTA_SCOPE = "__global__"
DEFAULT_CREDIT_PROVIDER = "gemini"
CREDIT_UNITS_FULL = 4
CREDIT_UNITS_FOLLOWUP = 1
VALID_USAGE_SOURCES = frozenset({"shared", "byok", "local"})

PROVIDER_CREDIT_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    ("gemini", "Gemini", "gemini_api_key", "gemini_model_name"),
    ("groq", "Groq", "groq_api_key", "groq_llm_model_name"),
    ("openrouter", "OpenRouter", "openrouter_api_key", "openrouter_model_name"),
    ("cerebras", "Cerebras", "cerebras_api_key", "cerebras_model_name"),
    ("mistral", "Mistral", "mistral_api_key", "mistral_model_name"),
    ("openai", "OpenAI", "openai_api_key", "openai_model_name"),
    ("claude", "Claude", "claude_api_key", "claude_model_name"),
    ("grok", "Grok", "grok_api_key", "grok_model_name"),
)

_PROVIDER_META: dict[str, tuple[str, str, str]] = {
    pid: (label, key_attr, model_attr) for pid, label, key_attr, model_attr in PROVIDER_CREDIT_CATALOG
}
_PROVIDER_ALIASES = {"anthropic": "claude", "xai": "grok"}


class _QuotaLimitReached(Exception):
    """Internal control-flow error to roll back partial savepoint credit updates."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return _utc_now().date()


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_provider(provider: str | None) -> str | None:
    cleaned = (provider or "").strip().lower()
    if not cleaned or cleaned == "auto":
        return None
    cleaned = _PROVIDER_ALIASES.get(cleaned, cleaned)
    return cleaned[:16]


def _configured_server_providers(settings: Settings) -> list[str]:
    """Return server-configured shared providers ordered by router preference."""
    raw_order = settings.llm_router_providers
    router_order = (
        [_normalize_provider(p) for p in raw_order.split(",") if p.strip()]
        if isinstance(raw_order, str)
        else [_normalize_provider(str(p)) for p in raw_order if str(p).strip()]
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for pid in [*router_order, *(item[0] for item in PROVIDER_CREDIT_CATALOG)]:
        if not pid or pid in seen or pid not in _PROVIDER_META:
            continue
        _, key_attr, _ = _PROVIDER_META[pid]
        if bool(getattr(settings, key_attr, None)):
            seen.add(pid)
            ordered.append(pid)
    return ordered


def _active_shared_providers(settings: Settings, byok_set: set[str] | None = None) -> list[str]:
    """Shared server providers available without user keys (falls back to default in tests)."""
    byok = {_normalize_provider(p) for p in (byok_set or set())} - {None}
    configured = _configured_server_providers(settings)
    if configured:
        return [p for p in configured if p not in byok]
    return [DEFAULT_CREDIT_PROVIDER] if not byok else []


def _credit_windows(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    """Compute fixed 3-hour and 2-day renewal windows and fixed per-user caps."""
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    short_hours = max(1, int(settings.llm_credits_short_window_hours))
    long_days = max(1, int(settings.llm_credits_long_window_days))

    epoch_hours = int(current_now.timestamp() // 3600)
    short_start_epoch_h = (epoch_hours // short_hours) * short_hours
    short_start = datetime.fromtimestamp(short_start_epoch_h * 3600, tz=timezone.utc)
    short_resets_at = short_start + timedelta(hours=short_hours)

    today_utc = current_now.date()
    long_start_ordinal = (today_utc.toordinal() // long_days) * long_days
    long_start_date = date.fromordinal(long_start_ordinal)
    long_resets_at = datetime.combine(
        long_start_date + timedelta(days=long_days),
        dt_time.min,
        tzinfo=timezone.utc,
    )

    long_cap = max(1, int(settings.llm_credits_2d_per_model))
    short_cap = min(long_cap, max(1, int(settings.llm_credits_3h_per_model)))

    return {
        "now": current_now,
        "short_hours": short_hours,
        "long_days": long_days,
        "short_usage_date": short_start.date(),
        "short_block_hour": short_start.hour,
        "short_resets_at": short_resets_at,
        "long_usage_date": long_start_date,
        "long_resets_at": long_resets_at,
        "short_cap": short_cap,
        "long_cap": long_cap,
        "short_cap_units": short_cap * CREDIT_UNITS_FULL,
        "long_cap_units": long_cap * CREDIT_UNITS_FULL,
    }


def _short_scope_key(provider: str, user_id: UUID, block_hour: int) -> str:
    return f"3hq:{block_hour:02d}:{provider[:16]}:{user_id.hex}"


def _long_scope_key(provider: str, user_id: UUID) -> str:
    return f"2dq:{provider[:16]}:{user_id.hex}"


def _receipt_scope_key(research_id: UUID, short_date: date, block_hour: int, provider: str) -> str:
    return f"rsv:{research_id.hex}:{short_date.strftime('%y%m%d')}:{block_hour:02d}:{provider[:16]}"


def _parse_receipt_row(row: DailyQuotaUsage) -> tuple[date, int, str, date] | None:
    parts = row.scope_key.split(":", 4)
    if len(parts) != 5 or parts[0] != "rsv":
        return None
    try:
        short_date = datetime.strptime(parts[2], "%y%m%d").date()
        short_hour = int(parts[3])
    except ValueError:
        return None
    return short_date, short_hour, parts[4], row.usage_date


def _remaining_pct(used: int, cap: int) -> int:
    if cap <= 0:
        return 0
    remaining = max(0, cap - max(0, used))
    if remaining <= 0:
        return 0
    if remaining >= cap:
        return 100
    return max(1, min(99, round((remaining / cap) * 100)))


def count_active_users(
    session: Session,
    *,
    user_id: UUID | None = None,
    usage_date: date | None = None,
    now: datetime | None = None,
) -> int:
    """Count active accounts for operational telemetry only (does not affect user credits)."""
    current_now = now or _utc_now()
    today = usage_date or current_now.date()

    active_session_exists = exists(
        select(AuthSession.token_hash).where(
            AuthSession.user_id == User.id,
            AuthSession.expires_at > current_now,
        )
    )
    used_today_exists = exists(
        select(ModelUsageDaily.id).where(
            ModelUsageDaily.user_id == User.id,
            ModelUsageDaily.usage_date == today,
        )
    )
    activity_clauses = [active_session_exists, used_today_exists]
    if user_id is not None:
        activity_clauses.append(User.id == user_id)

    count = session.execute(
        select(func.count(User.id)).where(
            User.is_active.is_(True),
            or_(*activity_clauses),
        )
    ).scalar_one()
    return max(1, int(count or 0))


def compute_quota_policy(
    session: Session,
    *,
    user_id: UUID | None = None,
    settings: Settings | None = None,
    usage_date: date | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Return the fixed per-user credit allowance (never scaled by user count)."""
    active_settings = settings or get_settings()
    windows = _credit_windows(active_settings, now=now)
    provider_count = max(1, len(_configured_server_providers(active_settings)))
    short_cap = windows["short_cap"]
    long_cap = windows["long_cap"]
    return {
        "enrolled_users": 1,
        "short_credits_per_model": short_cap,
        "long_credits_per_model": long_cap,
        "system_pool_total": long_cap * provider_count,
        "user_daily_request_cap": short_cap,
    }


def _dialect_name(session: Session) -> str:
    return session.bind.dialect.name if session.bind is not None else ""


def _acquire_sqlite_immediate_lock(session: Session) -> bool:
    """Upgrade an idle or pure-read SQLite session to an IMMEDIATE write transaction."""
    if _dialect_name(session) != "sqlite":
        return False
    if session.new or session.dirty or session.deleted:
        return False
    if session.in_transaction():
        conn = session.connection()
        driver_conn = getattr(conn.connection, "driver_connection", None)
        if getattr(driver_conn, "in_transaction", False):
            return False
        session.rollback()
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    return True


def _ensure_quota_scope_rows(
    session: Session,
    *,
    usage_date: date,
    scope_keys: list[str],
    now: datetime,
) -> None:
    dialect = _dialect_name(session)
    for scope_key in scope_keys:
        if dialect == "postgresql":
            stmt = (
                pg_insert(DailyQuotaUsage)
                .values(
                    id=uuid4(),
                    usage_date=usage_date,
                    scope_key=scope_key,
                    shared_requests_used=0,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_daily_quota_usage_date_scope")
            )
            session.execute(stmt)
        elif dialect == "sqlite":
            stmt = (
                sqlite_insert(DailyQuotaUsage)
                .values(
                    id=uuid4(),
                    usage_date=usage_date,
                    scope_key=scope_key,
                    shared_requests_used=0,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["usage_date", "scope_key"])
            )
            session.execute(stmt)
        else:
            existing = session.execute(
                select(DailyQuotaUsage.id).where(
                    DailyQuotaUsage.usage_date == usage_date,
                    DailyQuotaUsage.scope_key == scope_key,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    DailyQuotaUsage(
                        usage_date=usage_date,
                        scope_key=scope_key,
                        shared_requests_used=0,
                    )
                )
                session.flush()


def _read_scope_used(session: Session, *, usage_date: date, scope_key: str) -> int:
    value = session.execute(
        select(DailyQuotaUsage.shared_requests_used).where(
            DailyQuotaUsage.usage_date == usage_date,
            DailyQuotaUsage.scope_key == scope_key,
        )
    ).scalar_one_or_none()
    return int(value or 0)


def _try_increment_dual_buckets(
    session: Session,
    *,
    user_id: UUID,
    provider: str,
    windows: dict[str, Any],
    units: int = CREDIT_UNITS_FULL,
) -> bool:
    """Atomically increment both 3-hour and 2-day user+provider buckets inside a savepoint."""
    cost = max(1, int(units))
    now = windows["now"]
    short_date = windows["short_usage_date"]
    long_date = windows["long_usage_date"]
    short_key = _short_scope_key(provider, user_id, windows["short_block_hour"])
    long_key = _long_scope_key(provider, user_id)

    _ensure_quota_scope_rows(session, usage_date=short_date, scope_keys=[short_key], now=now)
    _ensure_quota_scope_rows(session, usage_date=long_date, scope_keys=[long_key], now=now)

    try:
        with session.begin_nested():
            short_res = session.execute(
                update(DailyQuotaUsage)
                .where(
                    DailyQuotaUsage.usage_date == short_date,
                    DailyQuotaUsage.scope_key == short_key,
                    DailyQuotaUsage.shared_requests_used <= windows["short_cap_units"] - cost,
                )
                .values(
                    shared_requests_used=DailyQuotaUsage.shared_requests_used + cost,
                    updated_at=now,
                )
            )
            if int(short_res.rowcount or 0) == 0:
                raise _QuotaLimitReached()

            long_res = session.execute(
                update(DailyQuotaUsage)
                .where(
                    DailyQuotaUsage.usage_date == long_date,
                    DailyQuotaUsage.scope_key == long_key,
                    DailyQuotaUsage.shared_requests_used <= windows["long_cap_units"] - cost,
                )
                .values(
                    shared_requests_used=DailyQuotaUsage.shared_requests_used + cost,
                    updated_at=now,
                )
            )
            if int(long_res.rowcount or 0) == 0:
                raise _QuotaLimitReached()
            return True
    except _QuotaLimitReached:
        return False


def _decrement_dual_buckets(
    session: Session,
    *,
    user_id: UUID,
    provider: str,
    short_date: date,
    short_hour: int,
    long_date: date,
    now: datetime,
    units: int = CREDIT_UNITS_FULL,
) -> None:
    refund = max(1, int(units))
    short_key = _short_scope_key(provider, user_id, short_hour)
    long_key = _long_scope_key(provider, user_id)
    session.execute(
        update(DailyQuotaUsage)
        .where(
            DailyQuotaUsage.usage_date == short_date,
            DailyQuotaUsage.scope_key == short_key,
            DailyQuotaUsage.shared_requests_used > 0,
        )
        .values(
            shared_requests_used=case(
                (DailyQuotaUsage.shared_requests_used >= refund, DailyQuotaUsage.shared_requests_used - refund),
                else_=0,
            ),
            updated_at=now,
        )
    )
    session.execute(
        update(DailyQuotaUsage)
        .where(
            DailyQuotaUsage.usage_date == long_date,
            DailyQuotaUsage.scope_key == long_key,
            DailyQuotaUsage.shared_requests_used > 0,
        )
        .values(
            shared_requests_used=case(
                (DailyQuotaUsage.shared_requests_used >= refund, DailyQuotaUsage.shared_requests_used - refund),
                else_=0,
            ),
            updated_at=now,
        )
    )


def _find_active_receipt_rows(session: Session, research_id: UUID) -> list[DailyQuotaUsage]:
    return list(
        session.execute(
            select(DailyQuotaUsage).where(
                DailyQuotaUsage.scope_key.like(f"rsv:{research_id.hex}:%"),
                DailyQuotaUsage.shared_requests_used > 0,
            )
        )
        .scalars()
        .all()
    )


def _attach_receipt_row(
    session: Session,
    *,
    research_id: UUID,
    windows: dict[str, Any],
    provider: str,
    units: int = CREDIT_UNITS_FULL,
) -> None:
    now = windows["now"]
    cost = max(1, int(units))
    receipt_key = _receipt_scope_key(
        research_id,
        windows["short_usage_date"],
        windows["short_block_hour"],
        provider,
    )
    _ensure_quota_scope_rows(
        session,
        usage_date=windows["long_usage_date"],
        scope_keys=[receipt_key],
        now=now,
    )
    session.execute(
        update(DailyQuotaUsage)
        .where(
            DailyQuotaUsage.usage_date == windows["long_usage_date"],
            DailyQuotaUsage.scope_key == receipt_key,
        )
        .values(shared_requests_used=cost, updated_at=now)
    )


def _default_provider(settings: Settings, provider: str | None) -> str:
    norm = _normalize_provider(provider)
    if norm:
        return norm
    configured = _configured_server_providers(settings)
    return configured[0] if configured else DEFAULT_CREDIT_PROVIDER


def reserve_shared_quota_slot(
    session: Session,
    *,
    user_id: UUID,
    provider: str | None = None,
    research_id: UUID | None = None,
    units: int = CREDIT_UNITS_FULL,
    settings: Settings | None = None,
    usage_date: date | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[bool, date, dict[str, Any]]:
    """Atomically reserve credit units for a user+provider across both 3-hour and 2-day windows."""
    active_settings = settings or get_settings()
    ref_now = now or _utc_now()
    if usage_date is not None and now is None:
        ref_now = datetime.combine(usage_date, ref_now.timetz()).astimezone(timezone.utc)
    windows = _credit_windows(active_settings, now=ref_now)
    prov = _default_provider(active_settings, provider)
    short_date = windows["short_usage_date"]
    long_date = windows["long_usage_date"]
    short_key = _short_scope_key(prov, user_id, windows["short_block_hour"])
    long_key = _long_scope_key(prov, user_id)

    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            reserved = _try_increment_dual_buckets(
                session,
                user_id=user_id,
                provider=prov,
                windows=windows,
                units=units,
            )
            if reserved and research_id is not None:
                _attach_receipt_row(
                    session,
                    research_id=research_id,
                    windows=windows,
                    provider=prov,
                    units=units,
                )

            short_used = _read_scope_used(session, usage_date=short_date, scope_key=short_key)
            long_used = _read_scope_used(session, usage_date=long_date, scope_key=long_key)
            snapshot = {
                "provider": prov,
                "short_used": short_used,
                "short_cap": windows["short_cap"],
                "long_used": long_used,
                "long_cap": windows["long_cap"],
                "short_resets_at": windows["short_resets_at"],
                "long_resets_at": windows["long_resets_at"],
                "shared_requests_used_today": short_used // CREDIT_UNITS_FULL,
                "user_daily_request_cap": windows["short_cap"],
            }
            if commit:
                session.commit()
            else:
                session.flush()
            return reserved, short_date, snapshot
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                session.rollback()
                sleep(0.02 * (attempt + 1))
                continue
            raise

    raise RuntimeError("Failed to acquire credit reservation lock after retries")


def release_shared_quota_slot(
    session: Session,
    *,
    user_id: UUID,
    usage_date: date,
    provider: str | None = None,
    short_hour: int | None = None,
    long_date: date | None = None,
    units: int = CREDIT_UNITS_FULL,
    settings: Settings | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    """Release previously reserved credit units from both 3-hour and 2-day windows."""
    active_settings = settings or get_settings()
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    prov = _default_provider(active_settings, provider)
    long_days = max(1, int(active_settings.llm_credits_long_window_days))
    resolved_long_date = long_date or date.fromordinal((usage_date.toordinal() // long_days) * long_days)
    short_hours = max(1, int(active_settings.llm_credits_short_window_hours))

    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            resolved_hour = short_hour
            if resolved_hour is None:
                candidate_hour = (current_now.hour // short_hours) * short_hours
                if _read_scope_used(
                    session,
                    usage_date=usage_date,
                    scope_key=_short_scope_key(prov, user_id, candidate_hour),
                ) > 0:
                    resolved_hour = candidate_hour
                else:
                    matching = session.execute(
                        select(DailyQuotaUsage.scope_key).where(
                            DailyQuotaUsage.usage_date == usage_date,
                            DailyQuotaUsage.scope_key.like(f"3hq:%:{prov[:16]}:{user_id.hex}"),
                            DailyQuotaUsage.shared_requests_used > 0,
                        )
                    ).scalar_one_or_none()
                    if matching:
                        try:
                            resolved_hour = int(matching.split(":")[1])
                        except (IndexError, ValueError):
                            resolved_hour = candidate_hour
                    else:
                        resolved_hour = candidate_hour

            _decrement_dual_buckets(
                session,
                user_id=user_id,
                provider=prov,
                short_date=usage_date,
                short_hour=resolved_hour,
                long_date=resolved_long_date,
                now=current_now,
                units=units,
            )
            if commit:
                session.commit()
            else:
                session.flush()
            return
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                session.rollback()
                sleep(0.02 * (attempt + 1))
                continue
            raise


def ensure_research_shared_quota(
    session: Session,
    *,
    research_id: UUID,
    user_id: UUID,
    provider: str,
    units: int = CREDIT_UNITS_FULL,
    settings: Settings | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> bool:
    """Ensure a shared reservation matches ``provider``, transferring from an earlier attempt if needed."""
    active_settings = settings or get_settings()
    norm_prov = _default_provider(active_settings, provider)
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    windows = _credit_windows(active_settings, now=current_now)
    cost = max(1, int(units))

    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            receipt_rows = _find_active_receipt_rows(session, research_id)
            parsed_receipts = [
                (row, parsed)
                for row in receipt_rows
                if (parsed := _parse_receipt_row(row)) is not None
            ]
            if any(parsed[2] == norm_prov for _, parsed in parsed_receipts):
                if commit:
                    session.commit()
                return True

            if not _try_increment_dual_buckets(
                session,
                user_id=user_id,
                provider=norm_prov,
                windows=windows,
                units=cost,
            ):
                if commit:
                    session.commit()
                return False

            for row, (old_short_date, old_short_hour, old_prov, old_long_date) in parsed_receipts:
                _decrement_dual_buckets(
                    session,
                    user_id=user_id,
                    provider=old_prov,
                    short_date=old_short_date,
                    short_hour=old_short_hour,
                    long_date=old_long_date,
                    now=current_now,
                    units=max(1, int(row.shared_requests_used or cost)),
                )
                row.shared_requests_used = 0
                row.updated_at = current_now

            _attach_receipt_row(
                session,
                research_id=research_id,
                windows=windows,
                provider=norm_prov,
                units=cost,
            )
            record = session.get(Research, research_id)
            if record is not None and cost == CREDIT_UNITS_FULL:
                record.shared_quota_reserved = True
                record.shared_quota_date = windows["short_usage_date"]
                session.add(record)

            if commit:
                session.commit()
            else:
                session.flush()
            return True
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                session.rollback()
                sleep(0.02 * (attempt + 1))
                continue
            raise

    raise RuntimeError("Failed to update research credit reservation after retries")


def settle_research_shared_quota(
    session: Session,
    *,
    research_id: UUID,
    user_id: UUID,
    actual_provider: str,
    units: int = CREDIT_UNITS_FULL,
    settings: Settings | None = None,
    now: datetime | None = None,
    commit: bool = False,
) -> None:
    """Confirm final credit deduction against ``actual_provider`` and close any tentative receipt."""
    active_settings = settings or get_settings()
    norm_prov = _default_provider(active_settings, actual_provider)
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    windows = _credit_windows(active_settings, now=current_now)
    cost = max(1, int(units))

    receipt_rows = _find_active_receipt_rows(session, research_id)
    matched = False
    for row in receipt_rows:
        parsed = _parse_receipt_row(row)
        row_units = max(1, int(row.shared_requests_used or cost))
        if parsed is None:
            row.shared_requests_used = 0
            continue
        old_short_date, old_short_hour, old_prov, old_long_date = parsed
        if old_prov == norm_prov and not matched:
            matched = True
        else:
            _decrement_dual_buckets(
                session,
                user_id=user_id,
                provider=old_prov,
                short_date=old_short_date,
                short_hour=old_short_hour,
                long_date=old_long_date,
                now=current_now,
                units=row_units,
            )
        row.shared_requests_used = 0
        row.updated_at = current_now

    if not matched:
        _increment_dual_buckets_unbounded(
            session,
            user_id=user_id,
            provider=norm_prov,
            windows=windows,
            units=cost,
        )

    record = session.get(Research, research_id)
    if record is not None and cost == CREDIT_UNITS_FULL and (
        record.shared_quota_reserved or record.shared_quota_date is not None
    ):
        record.shared_quota_reserved = False
        record.shared_quota_date = None
        session.add(record)

    if commit:
        session.commit()
    else:
        session.flush()


def release_research_shared_quota(
    session: Session,
    research_id: UUID,
    *,
    user_id: UUID | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    """Refund any pending shared-credit reservation attached to a failed or ungrounded run."""
    record = session.get(Research, research_id)
    owner_id = user_id or (record.user_id if record is not None else None)
    if owner_id is None:
        return
    receipt_rows = _find_active_receipt_rows(session, research_id)
    if not receipt_rows and (record is None or not record.shared_quota_reserved):
        return

    current_now = (now or _utc_now()).astimezone(timezone.utc)
    if receipt_rows:
        for row in receipt_rows:
            parsed = _parse_receipt_row(row)
            row_units = max(1, int(row.shared_requests_used or CREDIT_UNITS_FULL))
            if parsed is not None:
                short_date, short_hour, prov, long_date = parsed
                _decrement_dual_buckets(
                    session,
                    user_id=owner_id,
                    provider=prov,
                    short_date=short_date,
                    short_hour=short_hour,
                    long_date=long_date,
                    now=current_now,
                    units=row_units,
                )
            row.shared_requests_used = 0
            row.updated_at = current_now
    elif record is not None and record.shared_quota_date is not None:
        release_shared_quota_slot(
            session,
            user_id=owner_id,
            usage_date=record.shared_quota_date,
            provider=record.preferred_provider,
            settings=settings,
            now=current_now,
            commit=False,
        )

    if record is not None and (record.shared_quota_reserved or record.shared_quota_date is not None):
        record.shared_quota_reserved = False
        record.shared_quota_date = None
        session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()


def _increment_dual_buckets_unbounded(
    session: Session,
    *,
    user_id: UUID,
    provider: str,
    windows: dict[str, Any],
    units: int = CREDIT_UNITS_FULL,
) -> None:
    cost = max(1, int(units))
    now = windows["now"]
    short_date = windows["short_usage_date"]
    long_date = windows["long_usage_date"]
    short_key = _short_scope_key(provider, user_id, windows["short_block_hour"])
    long_key = _long_scope_key(provider, user_id)

    _ensure_quota_scope_rows(session, usage_date=short_date, scope_keys=[short_key], now=now)
    _ensure_quota_scope_rows(session, usage_date=long_date, scope_keys=[long_key], now=now)
    session.execute(
        update(DailyQuotaUsage)
        .where(DailyQuotaUsage.usage_date == short_date, DailyQuotaUsage.scope_key == short_key)
        .values(shared_requests_used=DailyQuotaUsage.shared_requests_used + cost, updated_at=now)
    )
    session.execute(
        update(DailyQuotaUsage)
        .where(DailyQuotaUsage.usage_date == long_date, DailyQuotaUsage.scope_key == long_key)
        .values(shared_requests_used=DailyQuotaUsage.shared_requests_used + cost, updated_at=now)
    )


def record_model_usage(
    session: Session,
    *,
    user_id: UUID,
    provider: str,
    model_name: str,
    usage_source: str = "shared",
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    increment_shared_quota: bool = False,
    units: int = CREDIT_UNITS_FULL,
    usage_date: date | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    """Persist per-day model usage rollup and optionally record shared credit consumption."""
    active_settings = settings or get_settings()
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    if usage_date is not None and now is None:
        current_now = datetime.combine(usage_date, current_now.timetz()).astimezone(timezone.utc)
    today = usage_date or current_now.date()
    norm_source = usage_source if usage_source in VALID_USAGE_SOURCES else "shared"
    norm_provider = _normalize_provider(provider) or (provider or "unknown").strip().lower()[:64] or "unknown"
    norm_model = (model_name or "unknown").strip()[:160] or "unknown"
    in_tok = max(0, int(input_tokens))
    out_tok = max(0, int(output_tokens))
    cost = max(0.0, float(estimated_cost_usd))

    dialect = _dialect_name(session)
    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            if dialect == "postgresql":
                stmt = (
                    pg_insert(ModelUsageDaily)
                    .values(
                        id=uuid4(),
                        usage_date=today,
                        user_id=user_id,
                        provider=norm_provider,
                        model_name=norm_model,
                        usage_source=norm_source,
                        request_count=1,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        estimated_cost_usd=cost,
                        last_used_at=current_now,
                        created_at=current_now,
                        updated_at=current_now,
                    )
                    .on_conflict_do_update(
                        constraint="uq_model_usage_daily_bucket",
                        set_={
                            "request_count": ModelUsageDaily.request_count + 1,
                            "input_tokens": ModelUsageDaily.input_tokens + in_tok,
                            "output_tokens": ModelUsageDaily.output_tokens + out_tok,
                            "estimated_cost_usd": ModelUsageDaily.estimated_cost_usd + cost,
                            "last_used_at": current_now,
                            "updated_at": current_now,
                        },
                    )
                )
                session.execute(stmt)
            elif dialect == "sqlite":
                stmt = (
                    sqlite_insert(ModelUsageDaily)
                    .values(
                        id=uuid4(),
                        usage_date=today,
                        user_id=user_id,
                        provider=norm_provider,
                        model_name=norm_model,
                        usage_source=norm_source,
                        request_count=1,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        estimated_cost_usd=cost,
                        last_used_at=current_now,
                        created_at=current_now,
                        updated_at=current_now,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            "usage_date",
                            "user_id",
                            "provider",
                            "model_name",
                            "usage_source",
                        ],
                        set_={
                            "request_count": ModelUsageDaily.request_count + 1,
                            "input_tokens": ModelUsageDaily.input_tokens + in_tok,
                            "output_tokens": ModelUsageDaily.output_tokens + out_tok,
                            "estimated_cost_usd": ModelUsageDaily.estimated_cost_usd + cost,
                            "last_used_at": current_now,
                            "updated_at": current_now,
                        },
                    )
                )
                session.execute(stmt)
            else:
                existing = session.execute(
                    select(ModelUsageDaily).where(
                        ModelUsageDaily.usage_date == today,
                        ModelUsageDaily.user_id == user_id,
                        ModelUsageDaily.provider == norm_provider,
                        ModelUsageDaily.model_name == norm_model,
                        ModelUsageDaily.usage_source == norm_source,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        ModelUsageDaily(
                            usage_date=today,
                            user_id=user_id,
                            provider=norm_provider,
                            model_name=norm_model,
                            usage_source=norm_source,
                            request_count=1,
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            estimated_cost_usd=cost,
                            last_used_at=current_now,
                        )
                    )
                else:
                    existing.request_count += 1
                    existing.input_tokens += in_tok
                    existing.output_tokens += out_tok
                    existing.estimated_cost_usd += cost
                    existing.last_used_at = current_now

            if increment_shared_quota and norm_source == "shared":
                windows = _credit_windows(active_settings, now=current_now)
                _increment_dual_buckets_unbounded(
                    session,
                    user_id=user_id,
                    provider=norm_provider,
                    windows=windows,
                    units=units,
                )

            if commit:
                session.commit()
            else:
                session.flush()
            return
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                session.rollback()
                sleep(0.02 * (attempt + 1))
                continue
            raise


def _load_user_credit_buckets(
    session: Session,
    *,
    user_id: UUID,
    windows: dict[str, Any],
) -> tuple[dict[str, int], dict[str, int]]:
    """Load current 3-hour and 2-day spent quarter-units per provider in one query."""
    short_date = windows["short_usage_date"]
    long_date = windows["long_usage_date"]
    short_prefix = f"3hq:{windows['short_block_hour']:02d}:"
    short_suffix = f":{user_id.hex}"

    rows = session.execute(
        select(DailyQuotaUsage.usage_date, DailyQuotaUsage.scope_key, DailyQuotaUsage.shared_requests_used).where(
            DailyQuotaUsage.usage_date.in_([short_date, long_date]),
            DailyQuotaUsage.scope_key.like(f"%:{user_id.hex}"),
        )
    ).all()

    short_used: dict[str, int] = {}
    long_used: dict[str, int] = {}
    for row_date, scope_key, used_val in rows:
        used = int(used_val or 0)
        if row_date == short_date and scope_key.startswith(short_prefix) and scope_key.endswith(short_suffix):
            prov = scope_key[len(short_prefix) : -len(short_suffix)]
            if prov:
                short_used[prov] = used
        elif row_date == long_date and scope_key.startswith("2dq:") and scope_key.endswith(short_suffix):
            prov = scope_key[4 : -len(short_suffix)]
            if prov:
                long_used[prov] = used
    return short_used, long_used


def get_user_model_usage_and_quota(
    session: Session,
    user_id: UUID,
    settings: Settings | None = None,
    *,
    byok_providers: set[str] | None = None,
    user_models: dict[str, str] | None = None,
    local_available: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute a user's fixed per-model 3-hour and 2-day credits and usage rollup."""
    active_settings = settings or get_settings()
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    today = current_now.date()
    windows = _credit_windows(active_settings, now=current_now)

    if byok_providers is None:
        byok_rows = session.execute(
            select(UserAPIKey.provider).where(
                UserAPIKey.user_id == user_id,
                UserAPIKey.is_active.is_(True),
            )
        ).scalars().all()
        byok_set = {_normalize_provider(p) for p in byok_rows} - {None}
    else:
        byok_set = {_normalize_provider(p) for p in byok_providers} - {None}

    if user_models is None:
        pref_rows = session.execute(
            select(UserModelPreference.provider, UserModelPreference.model_name).where(
                UserModelPreference.user_id == user_id
            )
        ).all()
        selected_models = {p: m for p, m in pref_rows if p and m}
    else:
        selected_models = dict(user_models)

    short_used_map, long_used_map = _load_user_credit_buckets(
        session,
        user_id=user_id,
        windows=windows,
    )
    configured_server = _configured_server_providers(active_settings)
    short_cap = windows["short_cap"]
    long_cap = windows["long_cap"]
    short_resets_at = windows["short_resets_at"]
    long_resets_at = windows["long_resets_at"]

    # Build credit status items ordered cleanly: configured/used providers in catalog order, plus local Ollama.
    candidate_ids: list[str] = []
    seen_ids: set[str] = set()
    for pid in [
        *configured_server,
        *(item[0] for item in PROVIDER_CREDIT_CATALOG),
    ]:
        if pid in seen_ids or pid not in _PROVIDER_META:
            continue
        _, key_attr, _ = _PROVIDER_META[pid]
        has_server = bool(getattr(active_settings, key_attr, None))
        has_byok = pid in byok_set
        has_bucket_usage = short_used_map.get(pid, 0) > 0 or long_used_map.get(pid, 0) > 0
        if has_server or has_byok or has_bucket_usage:
            seen_ids.add(pid)
            candidate_ids.append(pid)

    # In test/unconfigured setups with no keys saved anywhere, expose the default shared slot
    # so the credit status stays concrete and deterministic.
    if not candidate_ids and not local_available:
        candidate_ids.append(DEFAULT_CREDIT_PROVIDER)

    provider_credits: list[dict[str, Any]] = []
    for pid in candidate_ids:
        label, key_attr, model_attr = _PROVIDER_META[pid]
        has_byok = pid in byok_set
        model_name = selected_models.get(pid) or str(getattr(active_settings, model_attr, ""))
        if has_byok:
            provider_credits.append(
                {
                    "provider": pid,
                    "label": label,
                    "model_name": model_name,
                    "mode": "byok",
                    "unlimited": True,
                    "remaining_pct": 100,
                    "short_window_pct": 100,
                    "long_window_pct": 100,
                    "short_resets_at": short_resets_at,
                    "long_resets_at": long_resets_at,
                    "short_remaining": short_cap,
                    "short_cap": short_cap,
                    "long_remaining": long_cap,
                    "long_cap": long_cap,
                }
            )
            continue

        s_used_units = short_used_map.get(pid, 0)
        l_used_units = long_used_map.get(pid, 0)
        s_cap_units = windows["short_cap_units"]
        l_cap_units = windows["long_cap_units"]
        s_rem_units = max(0, s_cap_units - s_used_units)
        l_rem_units = max(0, l_cap_units - l_used_units)
        s_rem = s_rem_units // CREDIT_UNITS_FULL
        l_rem = l_rem_units // CREDIT_UNITS_FULL
        s_pct = _remaining_pct(s_used_units, s_cap_units)
        l_pct = _remaining_pct(l_used_units, l_cap_units)
        eff_pct = min(s_pct, l_pct)
        provider_credits.append(
            {
                "provider": pid,
                "label": label,
                "model_name": model_name,
                "mode": "shared",
                "unlimited": False,
                "remaining_pct": eff_pct,
                "short_window_pct": s_pct,
                "long_window_pct": l_pct,
                "short_resets_at": short_resets_at,
                "long_resets_at": long_resets_at,
                "short_remaining": s_rem,
                "short_cap": short_cap,
                "long_remaining": l_rem,
                "long_cap": long_cap,
            }
        )

    if local_available:
        provider_credits.append(
            {
                "provider": "ollama",
                "label": "Local Ollama",
                "model_name": selected_models.get("ollama") or active_settings.generation_model_name,
                "mode": "local",
                "unlimited": True,
                "remaining_pct": 100,
                "short_window_pct": 100,
                "long_window_pct": 100,
                "short_resets_at": short_resets_at,
                "long_resets_at": long_resets_at,
                "short_remaining": short_cap,
                "short_cap": short_cap,
                "long_remaining": long_cap,
                "long_cap": long_cap,
            }
        )

    shared_items = [item for item in provider_credits if item["mode"] == "shared"]
    if shared_items:
        avg_pct = round(sum(item["remaining_pct"] for item in shared_items) / len(shared_items))
        if any(item["remaining_pct"] > 0 for item in shared_items):
            overall_remaining_pct = max(1, avg_pct)
        else:
            overall_remaining_pct = 0
        shared_used_sum = sum((item["short_cap"] - item["short_remaining"]) for item in shared_items)
        shared_cap_sum = sum(item["short_cap"] for item in shared_items)
        shared_rem_sum = sum(min(item["short_remaining"], item["long_remaining"]) for item in shared_items)
    else:
        overall_remaining_pct = 100
        shared_used_sum = 0
        shared_cap_sum = short_cap
        shared_rem_sum = short_cap

    rows = session.execute(
        select(
            ModelUsageDaily.provider,
            ModelUsageDaily.model_name,
            func.coalesce(func.sum(ModelUsageDaily.request_count), 0),
            func.coalesce(
                func.sum(
                    case(
                        (ModelUsageDaily.usage_date == today, ModelUsageDaily.request_count),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (ModelUsageDaily.usage_date == today)
                            & (ModelUsageDaily.usage_source == "byok"),
                            ModelUsageDaily.request_count,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (ModelUsageDaily.usage_date == today)
                            & (ModelUsageDaily.usage_source == "local"),
                            ModelUsageDaily.request_count,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            ModelUsageDaily.usage_date == today,
                            ModelUsageDaily.input_tokens + ModelUsageDaily.output_tokens,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(ModelUsageDaily.input_tokens + ModelUsageDaily.output_tokens),
                0,
            ),
            func.coalesce(func.sum(ModelUsageDaily.estimated_cost_usd), 0.0),
            func.max(ModelUsageDaily.last_used_at),
        )
        .where(ModelUsageDaily.user_id == user_id)
        .group_by(ModelUsageDaily.provider, ModelUsageDaily.model_name)
        .order_by(
            func.coalesce(func.sum(ModelUsageDaily.request_count), 0).desc(),
            func.max(ModelUsageDaily.last_used_at).desc(),
        )
    ).all()

    byok_today = 0
    local_today = 0
    total_today = 0
    total_tokens_today = 0
    total_requests_all_time = 0
    total_tokens_all_time = 0
    models_list: list[dict[str, Any]] = []

    for (
        provider,
        model_name,
        reqs_total,
        reqs_today,
        byok_reqs_today,
        local_reqs_today,
        toks_today,
        toks_total,
        cost_usd,
        last_used_raw,
    ) in rows:
        reqs_total_i = int(reqs_total or 0)
        reqs_today_i = int(reqs_today or 0)
        toks_today_i = int(toks_today or 0)
        toks_total_i = int(toks_total or 0)
        byok_today += int(byok_reqs_today or 0)
        local_today += int(local_reqs_today or 0)
        total_today += reqs_today_i
        total_tokens_today += toks_today_i
        total_requests_all_time += reqs_total_i
        total_tokens_all_time += toks_total_i
        models_list.append(
            {
                "provider": provider,
                "model_name": model_name,
                "requests_today": reqs_today_i,
                "tokens_today": toks_today_i,
                "total_requests": reqs_total_i,
                "total_tokens": toks_total_i,
                "estimated_cost_usd": round(float(cost_usd or 0.0), 6),
                "last_used_at": _parse_dt(last_used_raw),
            }
        )

    return {
        "overall_remaining_pct": overall_remaining_pct,
        "short_window_hours": windows["short_hours"],
        "long_window_days": windows["long_days"],
        "short_credits_per_model": short_cap,
        "long_credits_per_model": long_cap,
        "short_resets_at": short_resets_at,
        "long_resets_at": long_resets_at,
        "provider_credits": provider_credits,
        "enrolled_users": 1,
        "shared_requests_used_today": shared_used_sum,
        "user_daily_request_cap": shared_cap_sum,
        "user_requests_remaining_today": shared_rem_sum,
        "system_pool_total": long_cap * max(1, len(shared_items)),
        "system_pool_used_today": sum(long_used_map.get(i["provider"], 0) for i in shared_items),
        "system_pool_remaining": sum(i["long_remaining"] for i in shared_items),
        "byok_requests_today": byok_today,
        "local_requests_today": local_today,
        "total_requests_today": total_today,
        "total_tokens_today": total_tokens_today,
        "total_requests_all_time": total_requests_all_time,
        "total_tokens_all_time": total_tokens_all_time,
        "resets_at": short_resets_at,
        "models": models_list,
    }


def _format_reset_delta(target: datetime, now: datetime) -> str:
    seconds = max(0, int((target - now).total_seconds()))
    if seconds >= 86400:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    mins = max(1, seconds // 60)
    return f"{mins}m"


def _raise_daily_quota_exceeded(
    quota: dict[str, Any],
    *,
    provider: str | None = None,
    now: datetime | None = None,
) -> NoReturn:
    current_now = (now or _utc_now()).astimezone(timezone.utc)
    target_credit = None
    if provider:
        target_credit = next(
            (item for item in quota.get("provider_credits", []) if item["provider"] == provider),
            None,
        )
    if target_credit is not None:
        if target_credit["long_remaining"] <= 0:
            window_label = f"{quota['long_window_days']}-day"
            reset_str = _format_reset_delta(quota["long_resets_at"], current_now)
        else:
            window_label = f"{quota['short_window_hours']}-hour"
            reset_str = _format_reset_delta(quota["short_resets_at"], current_now)
        msg = (
            f"{target_credit['label']} credits are at 0% for this {window_label} cycle "
            f"(refreshes in {reset_str}). Switch to another model, connect your own API key, "
            "or use Local Ollama for unlimited runs."
        )
    else:
        short_reset = _format_reset_delta(quota["short_resets_at"], current_now)
        long_reset = _format_reset_delta(quota["long_resets_at"], current_now)
        msg = (
            f"All shared model credits are currently at 0% (3-hour refresh in {short_reset}; "
            f"2-day refresh in {long_reset}). Connect your own API key or Local Ollama for unlimited runs."
        )
    raise AppError(
        msg,
        status_code=429,
        code="daily_model_quota_exceeded",
    )


def enforce_user_daily_model_quota(
    session: Session,
    *,
    user_id: UUID,
    preferred_provider: str | None = None,
    user_byok_providers: set[str] | dict[str, str] | None = None,
    local_enabled: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Read-only check verifying fixed per-model 3-hour and 2-day credits before a request."""
    active_settings = settings or get_settings()
    pref = _normalize_provider(preferred_provider)
    byok_raw = (
        user_byok_providers.keys()
        if isinstance(user_byok_providers, dict)
        else (user_byok_providers or set())
    )
    byok_set = {_normalize_provider(p) for p in byok_raw} - {None}

    quota = get_user_model_usage_and_quota(
        session,
        user_id,
        settings=active_settings,
        byok_providers=byok_set,
    )
    if pref == "ollama" or (pref is not None and pref in byok_set):
        return quota
    if pref is None and (byok_set or local_enabled):
        return quota

    credits_by_prov = {item["provider"]: item for item in quota["provider_credits"]}
    if pref is not None:
        item = credits_by_prov.get(pref)
        if item is None or item["remaining_pct"] > 0:
            return quota
        _raise_daily_quota_exceeded(quota, provider=pref)

    if any(item["mode"] == "shared" and item["remaining_pct"] > 0 for item in quota["provider_credits"]):
        return quota
    _raise_daily_quota_exceeded(quota)


def acquire_run_quota_policy(
    session: Session,
    *,
    user_id: UUID,
    preferred_provider: str | None = None,
    user_byok_providers: set[str] | dict[str, str] | None = None,
    local_enabled: bool = False,
    research_id: UUID | None = None,
    units: int = CREDIT_UNITS_FULL,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> tuple[bool, bool, date | None, dict[str, Any]]:
    """Determine shared-provider eligibility and atomically reserve credit units if needed.

    Returns ``(allow_shared_providers, shared_quota_reserved, shared_quota_date, quota)``.
    """
    active_settings = settings or get_settings()
    cost = max(1, int(units))
    pref = _normalize_provider(preferred_provider)
    byok_raw = (
        user_byok_providers.keys()
        if isinstance(user_byok_providers, dict)
        else (user_byok_providers or set())
    )
    byok_set = {_normalize_provider(p) for p in byok_raw} - {None}

    if pref == "ollama":
        quota = get_user_model_usage_and_quota(
            session,
            user_id,
            settings=active_settings,
            byok_providers=byok_set,
            now=now,
        )
        return False, False, None, quota

    shared_candidates = _active_shared_providers(active_settings, byok_set)
    has_byok_for_choice = (pref in byok_set) if pref else bool(byok_set)
    if has_byok_for_choice:
        windows = _credit_windows(active_settings, now=now)
        short_used_map, long_used_map = _load_user_credit_buckets(
            session,
            user_id=user_id,
            windows=windows,
        )
        quota = get_user_model_usage_and_quota(
            session,
            user_id,
            settings=active_settings,
            byok_providers=byok_set,
            now=now,
        )
        # Shared server fallback is allowed only if at least one non-BYOK server model can cover ``cost``.
        can_fall_back_to_shared = any(
            (windows["short_cap_units"] - short_used_map.get(prov, 0)) >= cost
            and (windows["long_cap_units"] - long_used_map.get(prov, 0)) >= cost
            for prov in shared_candidates
        )
        return can_fall_back_to_shared, False, None, quota

    candidates = [pref] if pref is not None else shared_candidates
    if not candidates:
        candidates = [DEFAULT_CREDIT_PROVIDER]

    for candidate in candidates:
        reserved, reserved_date, _ = reserve_shared_quota_slot(
            session,
            user_id=user_id,
            provider=candidate,
            research_id=research_id,
            units=cost,
            settings=active_settings,
            now=now,
            commit=True,
        )
        if reserved:
            quota = get_user_model_usage_and_quota(
                session,
                user_id,
                settings=active_settings,
                byok_providers=byok_set,
                now=now,
            )
            return True, True, reserved_date, quota

    quota = get_user_model_usage_and_quota(
        session,
        user_id,
        settings=active_settings,
        byok_providers=byok_set,
        now=now,
    )
    if local_enabled and pref is None:
        return False, False, None, quota

    _raise_daily_quota_exceeded(quota, provider=pref, now=now)
