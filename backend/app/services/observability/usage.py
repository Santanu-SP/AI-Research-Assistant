"""Atomic shared AI quota enforcement and SQL-aggregated daily model usage service."""

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
from app.models.research import Research
from app.models.usage import DailyQuotaUsage, ModelUsageDaily
from app.models.user import AuthSession, User


GLOBAL_QUOTA_SCOPE = "__global__"
VALID_USAGE_SOURCES = frozenset({"shared", "byok", "local"})
_SHARED_PROVIDER_KEY_ATTRS = (
    "gemini_api_key",
    "groq_api_key",
    "openrouter_api_key",
    "cerebras_api_key",
    "mistral_api_key",
    "openai_api_key",
    "claude_api_key",
    "grok_api_key",
)


class _QuotaLimitReached(Exception):
    """Internal control-flow error to roll back partial savepoint quota updates."""


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


def count_active_users(
    session: Session,
    *,
    user_id: UUID | None = None,
    usage_date: date | None = None,
    now: datetime | None = None,
) -> int:
    """Count active accounts only (live session or usage today, plus optional caller).

    Dormant historical accounts without an unexpired session and without model usage
    today do not dilute the shared daily quota pool.
    """
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


def _system_pool_total(settings: Settings) -> int:
    if settings.llm_daily_system_request_pool is not None:
        return max(1, int(settings.llm_daily_system_request_pool))
    configured_count = sum(
        1 for attr in _SHARED_PROVIDER_KEY_ATTRS if bool(getattr(settings, attr, None))
    )
    return max(1, configured_count) * max(1, int(settings.llm_daily_requests_per_provider))


def compute_quota_policy(
    session: Session,
    *,
    user_id: UUID | None = None,
    settings: Settings | None = None,
    usage_date: date | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Compute the shared pool size, active user count, and per-user fair-share cap."""
    active_settings = settings or get_settings()
    active_users = count_active_users(
        session,
        user_id=user_id,
        usage_date=usage_date,
        now=now,
    )
    system_pool_total = _system_pool_total(active_settings)
    user_daily_request_cap = max(1, system_pool_total // active_users)
    return {
        "enrolled_users": active_users,
        "system_pool_total": system_pool_total,
        "user_daily_request_cap": user_daily_request_cap,
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


def reserve_shared_quota_slot(
    session: Session,
    *,
    user_id: UUID,
    settings: Settings | None = None,
    usage_date: date | None = None,
    commit: bool = True,
) -> tuple[bool, date, dict[str, int]]:
    """Atomically reserve one request from today's global shared pool and user share.

    Returns ``(reserved, usage_date, policy_and_counts)``.
    Safe against concurrent requests on both PostgreSQL and SQLite and independent
    of telemetry settings.
    """
    active_settings = settings or get_settings()
    now = _utc_now()
    today = usage_date or now.date()
    user_scope = str(user_id)

    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            policy = compute_quota_policy(
                session,
                user_id=user_id,
                settings=active_settings,
                usage_date=today,
                now=now,
            )
            pool_total = policy["system_pool_total"]
            user_cap = policy["user_daily_request_cap"]
            if pool_total <= 0 or user_cap <= 0:
                if commit:
                    session.commit()
                return False, today, {
                    **policy,
                    "system_pool_used_today": _read_scope_used(
                        session, usage_date=today, scope_key=GLOBAL_QUOTA_SCOPE
                    ),
                    "shared_requests_used_today": _read_scope_used(
                        session, usage_date=today, scope_key=user_scope
                    ),
                }

            _ensure_quota_scope_rows(
                session,
                usage_date=today,
                scope_keys=[GLOBAL_QUOTA_SCOPE, user_scope],
                now=now,
            )

            reserved = False
            try:
                with session.begin_nested():
                    global_res = session.execute(
                        update(DailyQuotaUsage)
                        .where(
                            DailyQuotaUsage.usage_date == today,
                            DailyQuotaUsage.scope_key == GLOBAL_QUOTA_SCOPE,
                            DailyQuotaUsage.shared_requests_used < pool_total,
                        )
                        .values(
                            shared_requests_used=DailyQuotaUsage.shared_requests_used + 1,
                            updated_at=now,
                        )
                    )
                    if int(global_res.rowcount or 0) == 0:
                        raise _QuotaLimitReached()

                    user_res = session.execute(
                        update(DailyQuotaUsage)
                        .where(
                            DailyQuotaUsage.usage_date == today,
                            DailyQuotaUsage.scope_key == user_scope,
                            DailyQuotaUsage.shared_requests_used < user_cap,
                        )
                        .values(
                            shared_requests_used=DailyQuotaUsage.shared_requests_used + 1,
                            updated_at=now,
                        )
                    )
                    if int(user_res.rowcount or 0) == 0:
                        raise _QuotaLimitReached()
                    reserved = True
            except _QuotaLimitReached:
                reserved = False

            snapshot = {
                **policy,
                "system_pool_used_today": _read_scope_used(
                    session, usage_date=today, scope_key=GLOBAL_QUOTA_SCOPE
                ),
                "shared_requests_used_today": _read_scope_used(
                    session, usage_date=today, scope_key=user_scope
                ),
            }
            if commit:
                session.commit()
            else:
                session.flush()
            return reserved, today, snapshot
        except OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < 4:
                session.rollback()
                sleep(0.02 * (attempt + 1))
                continue
            raise

    raise RuntimeError("Failed to acquire quota lock after retries")


def release_shared_quota_slot(
    session: Session,
    *,
    user_id: UUID,
    usage_date: date,
    commit: bool = True,
) -> None:
    """Release one previously reserved shared quota slot (never going below zero)."""
    now = _utc_now()
    user_scope = str(user_id)
    for attempt in range(5):
        try:
            _acquire_sqlite_immediate_lock(session)
            for scope_key in (GLOBAL_QUOTA_SCOPE, user_scope):
                session.execute(
                    update(DailyQuotaUsage)
                    .where(
                        DailyQuotaUsage.usage_date == usage_date,
                        DailyQuotaUsage.scope_key == scope_key,
                        DailyQuotaUsage.shared_requests_used > 0,
                    )
                    .values(
                        shared_requests_used=DailyQuotaUsage.shared_requests_used - 1,
                        updated_at=now,
                    )
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


def release_research_shared_quota(
    session: Session,
    research_id: UUID,
    *,
    commit: bool = True,
) -> None:
    """Release an unused shared-quota reservation attached to a Research run."""
    record = session.get(Research, research_id)
    if (
        record is None
        or not record.shared_quota_reserved
        or record.user_id is None
        or record.shared_quota_date is None
    ):
        return
    release_shared_quota_slot(
        session,
        user_id=record.user_id,
        usage_date=record.shared_quota_date,
        commit=False,
    )
    record.shared_quota_reserved = False
    record.shared_quota_date = None
    session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()


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
    usage_date: date | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    """Persist per-day model usage rollup independently of telemetry settings."""
    current_now = now or _utc_now()
    today = usage_date or current_now.date()
    norm_source = usage_source if usage_source in VALID_USAGE_SOURCES else "shared"
    norm_provider = (provider or "unknown").strip()[:64] or "unknown"
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
                user_scope = str(user_id)
                _ensure_quota_scope_rows(
                    session,
                    usage_date=today,
                    scope_keys=[GLOBAL_QUOTA_SCOPE, user_scope],
                    now=current_now,
                )
                for scope_key in (GLOBAL_QUOTA_SCOPE, user_scope):
                    session.execute(
                        update(DailyQuotaUsage)
                        .where(
                            DailyQuotaUsage.usage_date == today,
                            DailyQuotaUsage.scope_key == scope_key,
                        )
                        .values(
                            shared_requests_used=DailyQuotaUsage.shared_requests_used + 1,
                            updated_at=current_now,
                        )
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


def get_user_model_usage_and_quota(
    session: Session,
    user_id: UUID,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compute a user's model usage and fair-share daily shared-key quota via SQL rollup."""
    active_settings = settings or get_settings()
    now = _utc_now()
    today = now.date()

    policy = compute_quota_policy(
        session,
        user_id=user_id,
        settings=active_settings,
        usage_date=today,
        now=now,
    )
    active_users = policy["enrolled_users"]
    system_pool_total = policy["system_pool_total"]
    fair_share = policy["user_daily_request_cap"]

    system_pool_used_today = _read_scope_used(
        session, usage_date=today, scope_key=GLOBAL_QUOTA_SCOPE
    )
    shared_used_today = _read_scope_used(session, usage_date=today, scope_key=str(user_id))
    system_pool_remaining = max(0, system_pool_total - system_pool_used_today)
    available_budget = system_pool_remaining + shared_used_today
    user_daily_request_cap = max(shared_used_today, min(fair_share, available_budget))
    user_requests_remaining = max(
        0,
        min(user_daily_request_cap - shared_used_today, system_pool_remaining),
    )

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

    resets_at = datetime.combine(today + timedelta(days=1), dt_time.min, tzinfo=timezone.utc)
    return {
        "enrolled_users": active_users,
        "shared_requests_used_today": shared_used_today,
        "user_daily_request_cap": user_daily_request_cap,
        "user_requests_remaining_today": user_requests_remaining,
        "system_pool_total": system_pool_total,
        "system_pool_used_today": system_pool_used_today,
        "system_pool_remaining": system_pool_remaining,
        "byok_requests_today": byok_today,
        "local_requests_today": local_today,
        "total_requests_today": total_today,
        "total_tokens_today": total_tokens_today,
        "total_requests_all_time": total_requests_all_time,
        "total_tokens_all_time": total_tokens_all_time,
        "resets_at": resets_at,
        "models": models_list,
    }


def _raise_daily_quota_exceeded(quota: dict[str, Any]) -> NoReturn:
    active_count = quota["enrolled_users"]
    raise AppError(
        (
            f"Daily shared AI request quota reached ({quota['shared_requests_used_today']}/"
            f"{quota['user_daily_request_cap']} used today, shared pool "
            f"{quota['system_pool_remaining']}/{quota['system_pool_total']} left "
            f"across {active_count} active user{'s' if active_count != 1 else ''}). "
            "Connect your own API key (BYOK) or Local Ollama for unlimited requests."
        ),
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
    """Read-only guard verifying whether a request may proceed under today's quota."""
    pref = (preferred_provider or "").strip().lower() or None
    if pref == "auto":
        pref = None
    if pref == "ollama":
        return get_user_model_usage_and_quota(session, user_id, settings=settings)

    byok_set = set(user_byok_providers.keys() if isinstance(user_byok_providers, dict) else (user_byok_providers or set()))
    has_byok_for_choice = (pref in byok_set) if pref else bool(byok_set)
    quota = get_user_model_usage_and_quota(session, user_id, settings=settings)
    if has_byok_for_choice or (local_enabled and pref is None):
        return quota
    if quota["user_requests_remaining_today"] > 0 and quota["system_pool_remaining"] > 0:
        return quota
    _raise_daily_quota_exceeded(quota)


def acquire_run_quota_policy(
    session: Session,
    *,
    user_id: UUID,
    preferred_provider: str | None = None,
    user_byok_providers: set[str] | dict[str, str] | None = None,
    local_enabled: bool = False,
    settings: Settings | None = None,
) -> tuple[bool, bool, date | None, dict[str, Any]]:
    """Determine shared-provider eligibility and atomically reserve a slot when needed.

    Returns ``(allow_shared_providers, shared_quota_reserved, shared_quota_date, quota)``.
    When daily shared quota is exhausted, shared server keys are strictly disabled
    even if the user supplied their own BYOK key (preventing failing-BYOK fallthrough).
    """
    active_settings = settings or get_settings()
    pref = (preferred_provider or "").strip().lower() or None
    if pref == "auto":
        pref = None

    byok_set = set(
        user_byok_providers.keys()
        if isinstance(user_byok_providers, dict)
        else (user_byok_providers or set())
    )

    if pref == "ollama":
        quota = get_user_model_usage_and_quota(session, user_id, settings=active_settings)
        return False, False, None, quota

    has_byok_for_choice = (pref in byok_set) if pref else bool(byok_set)
    if has_byok_for_choice:
        quota = get_user_model_usage_and_quota(session, user_id, settings=active_settings)
        can_fall_back_to_shared = (
            quota["user_requests_remaining_today"] > 0
            and quota["system_pool_remaining"] > 0
        )
        # Never pre-consume a shared slot while user starts with their own BYOK key;
        # router's before_shared_attempt callback reserves atomically only on fallback.
        return can_fall_back_to_shared, False, None, quota

    reserved, reserved_date, snapshot = reserve_shared_quota_slot(
        session,
        user_id=user_id,
        settings=active_settings,
        commit=True,
    )
    if reserved:
        quota = get_user_model_usage_and_quota(session, user_id, settings=active_settings)
        return True, True, reserved_date, quota

    if local_enabled and pref is None:
        quota = get_user_model_usage_and_quota(session, user_id, settings=active_settings)
        return False, False, None, quota

    quota = get_user_model_usage_and_quota(session, user_id, settings=active_settings)
    # Build accurate error from current state + snapshot just in case
    if quota["shared_requests_used_today"] == 0 and snapshot.get("shared_requests_used_today", 0) > 0:
        quota["shared_requests_used_today"] = snapshot["shared_requests_used_today"]
    _raise_daily_quota_exceeded(quota)
