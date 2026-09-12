from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
import app.models  # noqa: F401 - registers models with Base metadata


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def test_settings(tmp_path: Path, upload_dir: Path) -> Settings:
    return Settings(
        app_environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:3000"],
        document_upload_dir=upload_dir,
        document_max_upload_bytes=64,
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
def test_app(test_settings: Settings) -> Generator[FastAPI, None, None]:
    application = create_app(test_settings)
    Base.metadata.create_all(application.state.db_engine)
    try:
        yield application
    finally:
        Base.metadata.drop_all(application.state.db_engine)


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
