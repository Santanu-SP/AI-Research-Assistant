from collections.abc import Generator
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus, DocumentType
from app.models.document import Document, DocumentChunk
from app.models.project import ResearchProject
from app.models.user import User
from app.services.retrieval import keyword_search, retrieve, semantic_search

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FixedEmbeddingService:
    dimension = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0] + [0.0] * 1023


@pytest.fixture(scope="module")
def postgres_session() -> Generator[Session, None, None]:
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")

    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql":
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use PostgreSQL")
    if not parsed.database or "test" not in parsed.database.lower():
        pytest.fail(
            "POSTGRES_TEST_DATABASE_URL must point to a dedicated database "
            "whose name contains 'test'"
        )

    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option(
        "sqlalchemy.url",
        database_url.replace("%", "%%"),
    )
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        command.downgrade(alembic_config, "base")


def _document(
    *,
    user_id,
    project_id,
    name: str,
    text_value: str,
) -> Document:
    document = Document(
        user_id=user_id,
        project_id=project_id,
        name=f"{name}.pdf",
        stored_name=f"{uuid4().hex}.pdf",
        file_type=DocumentType.PDF,
        mime_type="application/pdf",
        size=100,
        status=DocumentStatus.INDEXED,
        title=name,
        page_count=1,
    )
    document.chunks.append(
        DocumentChunk(
            node_id=str(uuid4()),
            text=text_value,
            page=1,
            section="Test",
            chunk_index=0,
            embedding=[1.0] + [0.0] * 1023,
        )
    )
    return document


def test_postgres_project_scoped_vector_fts_and_gin_index(
    postgres_session: Session,
) -> None:
    user_a = User(name="User A", email="pg-user-a@example.test")
    user_b = User(name="User B", email="pg-user-b@example.test")
    alpha = ResearchProject(user=user_a, name="Alpha")
    beta = ResearchProject(user=user_a, name="Beta")
    gamma = ResearchProject(user=user_b, name="Gamma")
    postgres_session.add_all([user_a, user_b, alpha, beta, gamma])
    postgres_session.flush()
    alpha_document = _document(
        user_id=user_a.id,
        project_id=alpha.id,
        name="Alpha transformer",
        text_value="transformer attention mechanism",
    )
    beta_document = _document(
        user_id=user_a.id,
        project_id=beta.id,
        name="Beta quantum",
        text_value="quantum entanglement experiment",
    )
    gamma_document = _document(
        user_id=user_b.id,
        project_id=gamma.id,
        name="Gamma transformer",
        text_value="transformer attention mechanism with a higher lexical match",
    )
    postgres_session.add_all([alpha_document, beta_document, gamma_document])
    postgres_session.commit()

    alpha_vector = semantic_search(
        postgres_session,
        user_a.id,
        [1.0] + [0.0] * 1023,
        10,
        alpha.id,
    )
    alpha_keyword = keyword_search(
        postgres_session,
        user_a.id,
        "transformer attention",
        10,
        alpha.id,
    )
    beta_keyword = keyword_search(
        postgres_session,
        user_a.id,
        "transformer attention",
        10,
        beta.id,
    )

    assert [item.chunk.document_id for item in alpha_vector] == [alpha_document.id]
    assert [item.chunk.document_id for item in alpha_keyword] == [alpha_document.id]
    assert beta_keyword == []

    candidates = retrieve(
        postgres_session,
        user_a.id,
        "transformer attention",
        Settings(database_url=str(postgres_session.bind.url)),
        FixedEmbeddingService(),
        project_id=alpha.id,
    )
    assert {item.document_id for item in candidates} == {alpha_document.id}
    assert {item.project_id for item in candidates} == {alpha.id}

    with pytest.raises(AppError) as error:
        retrieve(
            postgres_session,
            user_b.id,
            "transformer attention",
            Settings(database_url=str(postgres_session.bind.url)),
            FixedEmbeddingService(),
            project_id=alpha.id,
        )
    assert error.value.code == "research_project_not_found"

    assert postgres_session.scalar(
        text(
            "SELECT search_vector IS NOT NULL FROM document_chunks "
            "WHERE document_id = :document_id"
        ),
        {"document_id": alpha_document.id},
    )
    index_definition = postgres_session.scalar(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "AND indexname = 'ix_document_chunks_search_vector_gin'"
        )
    )
    assert index_definition is not None
    assert "USING gin" in index_definition
