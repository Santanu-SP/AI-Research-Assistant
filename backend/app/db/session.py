"""SQLAlchemy engine construction, session factory, and FastAPI DB dependency."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def _is_sqlite_url(database_url: str) -> bool:
    """Check whether the target database URL uses the SQLite dialect."""
    return make_url(database_url).get_backend_name() == "sqlite"


def create_db_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine suitable for SQLite locally and PostgreSQL in production."""
    is_sqlite = _is_sqlite_url(database_url)
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy ``sessionmaker`` bound to the given engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields one isolated SQLAlchemy session per HTTP request."""
    session_factory = request.app.state.db_session_factory
    with session_factory() as session:
        yield session