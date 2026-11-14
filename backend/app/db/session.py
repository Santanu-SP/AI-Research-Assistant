from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Normalize PostgreSQL URLs to use psycopg v3 and enforce TLS on Neon hosts."""
    raw = database_url.strip()
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw[len("postgres://") :]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://") :]

    url = make_url(raw)
    if url.get_backend_name() == "postgresql":
        host = (url.host or "").lower()
        query = dict(url.query)
        if host.endswith(".neon.tech") and "sslmode" not in query:
            query["sslmode"] = "require"
            url = url.set(query=query)
        return url.render_as_string(hide_password=False)
    return raw


def is_neon_pooled_url(database_url: str) -> bool:
    """Detect Neon PgBouncer pooled endpoints (``-pooler`` in hostname)."""
    try:
        host = (make_url(database_url).host or "").lower()
    except Exception:
        return False
    return "-pooler." in host and host.endswith(".neon.tech")


def create_db_engine(
    database_url: str,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
    pool_recycle: int | None = 300,
    pool_use_lifo: bool = True,
) -> Engine:
    """Create an engine suitable for SQLite locally and Neon/Supabase PostgreSQL in production."""

    normalized_url = normalize_database_url(database_url)
    url = make_url(normalized_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    options: dict[str, Any] = {"pool_pre_ping": True}
    if is_sqlite:
        options["connect_args"] = {"check_same_thread": False, "timeout": 15.0}
    else:
        if pool_size is not None:
            options["pool_size"] = pool_size
        if max_overflow is not None:
            options["max_overflow"] = max_overflow
        if pool_timeout is not None:
            options["pool_timeout"] = pool_timeout
        if pool_recycle is not None:
            options["pool_recycle"] = pool_recycle
        options["pool_use_lifo"] = pool_use_lifo
        # Neon's transaction pooler (PgBouncer) requires disabling server-side
        # prepared statement caching in psycopg3 when statements cross transactions.
        if is_neon_pooled_url(normalized_url):
            options["connect_args"] = {"prepare_threshold": None}

    engine = create_engine(normalized_url, **options)
    if is_sqlite:
        # SQLite does not enforce foreign keys unless explicitly enabled for
        # every connection. This keeps local/test cascade behavior truthful.
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db(request: Request) -> AsyncGenerator[Session, None]:
    """Provide one SQLAlchemy session per request.

    This is deliberately an *async* generator. FastAPI runs sync generator
    dependencies (and their cleanup) on the shared thread pool; under load
    every pool thread could be busy waiting for a DB connection while the
    cleanup that would return one waits for a free thread. Closing the
    session on the event loop removes that deadlock.
    """

    session_factory = request.app.state.db_session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
