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
from app.services.rag.embeddings import EmbeddingService, embedding_service_for
from app.services.research import projects as project_service

# Standard reciprocal-rank fusion constant. A larger k softens the penalty
# for a result that only one of the two lists ranked highly.
RRF_K = 60
FTS_CONFIGURATION = "english"


@dataclass(frozen=True)
class RankedChunk:
    chunk: DocumentChunk
    vector_score: float | None = None
    keyword_score: float | None = None


def _require_postgres(session: Session) -> None:
    dialect = None if session.bind is None else session.bind.dialect.name
    if dialect != "postgresql":
        raise AppError(
            "Retrieval requires PostgreSQL with pgvector",
            status_code=503,
            code="retrieval_backend_unavailable",
        )


def _reciprocal_rank(rank: int) -> float:
    return 1 / (RRF_K + rank)


def semantic_search(
    session: Session,
    user_id: UUID,
    query_vector: list[float],
    limit: int,
    project_id: UUID | None = None,
) -> list[RankedChunk]:
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
        RankedChunk(chunk=row[0], vector_score=1 - float(row[1]))
        for row in rows
    ]


def keyword_search(
    session: Session,
    user_id: UUID,
    query: str,
    limit: int,
    project_id: UUID | None = None,
) -> list[RankedChunk]:
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
        RankedChunk(chunk=row[0], keyword_score=float(row[1]))
        for row in rows
    ]


def fuse(
    vector_results: list[RankedChunk],
    keyword_results: list[RankedChunk],
    limit: int,
) -> list[RankedChunk]:
    merged: dict[UUID, RankedChunk] = {}
    scores: dict[UUID, float] = {}
    ranked_lists = (
        (vector_results, "vector_score"),
        (keyword_results, "keyword_score"),
    )
    for results, score_field in ranked_lists:
        for rank, item in enumerate(results, start=1):
            chunk_id = item.chunk.id
            existing = merged.get(chunk_id)
            if existing is None:
                merged[chunk_id] = item
            else:
                incoming_score = getattr(item, score_field)
                merged[chunk_id] = replace(existing, **{score_field: incoming_score})
            scores[chunk_id] = scores.get(chunk_id, 0.0) + _reciprocal_rank(rank)

    ranked = sorted(
        merged.values(),
        key=lambda item: (-scores[item.chunk.id], str(item.chunk.id)),
    )
    return ranked[:limit]


def _hybrid_score(
    chunk_id: UUID,
    vector_ranks: dict[UUID, int],
    keyword_ranks: dict[UUID, int],
) -> float:
    score = 0.0
    if chunk_id in vector_ranks:
        score += _reciprocal_rank(vector_ranks[chunk_id])
    if chunk_id in keyword_ranks:
        score += _reciprocal_rank(keyword_ranks[chunk_id])
    return score


def retrieve(
    session: Session,
    user_id: UUID,
    query: str,
    settings: Settings,
    embeddings: EmbeddingService | None = None,
    *,
    project_id: UUID | None = None,
) -> list[RetrievalCandidate]:
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
    vector_ranks = {
        item.chunk.id: index for index, item in enumerate(vector_results, start=1)
    }
    keyword_ranks = {
        item.chunk.id: index for index, item in enumerate(keyword_results, start=1)
    }

    result: list[RetrievalCandidate] = []
    for item in candidates:
        document = item.chunk.document
        score = _hybrid_score(item.chunk.id, vector_ranks, keyword_ranks)
        result.append(
            RetrievalCandidate(
                chunk_id=item.chunk.id,
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
