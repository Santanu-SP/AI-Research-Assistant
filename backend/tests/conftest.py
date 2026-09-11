from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        app_environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:3000"],
    )


@pytest.fixture
def db_engine(test_settings: Settings) -> Generator[Engine, None, None]:
    engine = create_db_engine(test_settings.database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(db_engine)


@pytest.fixture
def db_session(
    db_session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    with db_session_factory() as session:
        yield session


@pytest.fixture
def test_app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
