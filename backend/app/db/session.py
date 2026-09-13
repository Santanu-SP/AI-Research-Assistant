from collections.abc import Generator
from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    """Create an engine suitable for SQLite locally and PostgreSQL later."""

    connect_args = (
        {"check_same_thread": False}
        if make_url(database_url).get_backend_name() == "sqlite"
        else {}
    )
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if make_url(database_url).get_backend_name() == "sqlite":
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


def get_db(request: Request) -> Generator[Session, None, None]:
    """Provide one SQLAlchemy session per request."""

    session_factory = request.app.state.db_session_factory
    with session_factory() as session:
        yield session
