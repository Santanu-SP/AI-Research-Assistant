from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(
    database_url: str,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: float | None = None,
) -> Engine:
    """Create an engine suitable for SQLite locally and PostgreSQL later."""

    is_sqlite = make_url(database_url).get_backend_name() == "sqlite"
    options: dict[str, Any] = {"pool_pre_ping": True}
    if is_sqlite:
        options["connect_args"] = {"check_same_thread": False}
    else:
        if pool_size is not None:
            options["pool_size"] = pool_size
        if max_overflow is not None:
            options["max_overflow"] = max_overflow
        if pool_timeout is not None:
            options["pool_timeout"] = pool_timeout
    engine = create_engine(database_url, **options)
    if is_sqlite:
        # SQLite does not enforce foreign keys unless explicitly enabled for
        # every connection. This keeps local/test cascade behavior truthful.
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
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
