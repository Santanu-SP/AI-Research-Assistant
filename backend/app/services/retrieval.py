"""PostgreSQL hybrid retrieval scoped by user and optional research project."""

from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus
from app.models.document import Document, DocumentChunk
from app.schemas.retrieval import RetrievalCandidate
from app.services import projects as project_service
from app.services.embeddings import EmbeddingService, embedding_service_for

RRF_K = 60
FTS_CONFIGURATION = "english"


@dataclass(frozen=True)
class RankedChunk:
    """Intermediate retrieval result holding a chunk and its individual search scores."""

    chunk: DocumentChunk
    vector_score: float | None = None
    keyword_score: float | None = None


def _require_postgres(session: Session) -> None:
    """Ensure the active SQLAlchemy session is bound to a PostgreSQL database."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise AppError(
            "Retrieval requires PostgreSQL with pgvector",
            status_code=503,
            code="retrieval_backend_unavailable",
        )


def _rrf_contribution(rank: int | None) -> float:
    """Compute the Reciprocal Rank Fusion score contribution for a 1-based rank."""
    if rank is None:
        return 0.0
    return 1 / (RRF_K + rank)


def semantic_search(
    session: Session,
    user_id: UUID,
    query_vector: list[float],
    limit: int,
    project_id: UUID | None = None,
) -> list[RankedChunk]:
    """Execute dense cosine similarity search over indexed chunks using pgvector."""
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        DocumentChunk.embedding.is_not(None),
    ]
    if project_id is not None:
        filters.append(Document.project_id == project_id)

    rows = session.execute(
        select(DocumentChunk, distance.label("distance"))
        .join(Document)
        .where(*filters)
        .order_by(distance, DocumentChunk.id)
        .limit(limit)
    ).all()
    return [
        RankedChunk(chunk=row[0], vector_score=1 - float(row[1])) for row in rows
    ]


def keyword_search(
    session: Session,
    user_id: UUID,
    query: str,
    limit: int,
    project_id: UUID | None = None,
) -> list[RankedChunk]:
    """Execute lexical full-text search over indexed chunks using PostgreSQL TSVECTOR."""
    query_expression = func.websearch_to_tsquery(FTS_CONFIGURATION, query)
    rank = func.ts_rank_cd(DocumentChunk.search_vector, query_expression)
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        DocumentChunk.search_vector.op("@@")(query_expression),
    ]
    if project_id is not None:
        filters.append(Document.project_id == project_id)

    rows = session.execute(
        select(DocumentChunk, rank.label("rank"))
        .join(Document)
        .where(*filters)
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(limit)
    ).all()
    return [
        RankedChunk(chunk=row[0], keyword_score=float(row[1])) for row in rows
    ]


def fuse(
    vector_results: list[RankedChunk],
    keyword_results: list[RankedChunk],
    limit: int,
) -> list[RankedChunk]:
    """Merge semantic and keyword search results using Reciprocal Rank Fusion (RRF)."""
    merged: dict[UUID, RankedChunk] = {}
    scores: dict[UUID, float] = {}

    for result_set, score_name in (
        (vector_results, "vector_score"),
        (keyword_results, "keyword_score"),
    ):
        for rank, item in enumerate(result_set, start=1):
            key = item.chunk.id
            previous = merged.get(key)
            merged[key] = (
                item
                if previous is None
                else replace(previous, **{score_name: getattr(item, score_name)})
            )
            scores[key] = scores.get(key, 0.0) + _rrf_contribution(rank)

    return sorted(
        merged.values(),
        key=lambda item: (-scores[item.chunk.id], str(item.chunk.id)),
    )[:limit]


def retrieve(
    session: Session,
    user_id: UUID,
    query: str,
    settings: Settings,
    embeddings: EmbeddingService | None = None,
    *,
    project_id: UUID | None = None,
) -> list[RetrievalCandidate]:
    """Run hybrid semantic + keyword retrieval and return fused ``RetrievalCandidate`` items."""
    normalized = query.strip()
    if not normalized:
        raise AppError(
            "A retrieval query is required",
            status_code=422,
            code="retrieval_query_required",
        )
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)

    _require_postgres(session)
    service = embeddings or embedding_service_for(settings)

    vector_results = semantic_search(
        session,
        user_id,
        service.embed_query(normalized),
        settings.vector_top_k,
        project_id,
    )
    keyword_results = keyword_search(
        session,
        user_id,
        normalized,
        settings.keyword_top_k,
        project_id,
    )
    candidates = fuse(vector_results, keyword_results, settings.hybrid_candidate_k)

    vector_rank = {
        item.chunk.id: index for index, item in enumerate(vector_results, 1)
    }
    keyword_rank = {
        item.chunk.id: index for index, item in enumerate(keyword_results, 1)
    }

    result: list[RetrievalCandidate] = []
    for item in candidates:
        chunk_id = item.chunk.id
        document = item.chunk.document
        score = _rrf_contribution(vector_rank.get(chunk_id)) + _rrf_contribution(
            keyword_rank.get(chunk_id)
        )
        result.append(
            RetrievalCandidate(
                chunk_id=chunk_id,
                node_id=item.chunk.node_id,
                document_id=document.id,
                project_id=document.project_id,
                source_type=document.source_type,
                content_level=document.content_level,
                paper_title=document.title or document.name,
                authors=document.authors,
                doi=document.doi,
                page=item.chunk.page,
                page_end=item.chunk.page_end,
                section=item.chunk.section,
                section_path=item.chunk.section_path,
                text=item.chunk.text,
                vector_score=item.vector_score,
                keyword_score=item.keyword_score,
                hybrid_score=score,
            )
        )
    return result