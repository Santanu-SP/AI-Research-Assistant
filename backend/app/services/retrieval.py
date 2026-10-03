"""PostgreSQL hybrid retrieval scoped by user and optional research project."""

from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus
from app.models.document import Document, DocumentChunk
from app.schemas.retrieval import RetrievalCandidate, RetrievalFilters
from app.services.embeddings import EmbeddingService, embedding_service_for
from app.services.doi import normalize_doi
from app.services import projects as project_service

RRF_K = 60
FTS_CONFIGURATION = "english"


@dataclass(frozen=True)
class RankedChunk:
    chunk: DocumentChunk
    vector_score: float | None = None
    keyword_score: float | None = None


def _require_postgres(session: Session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise AppError("Retrieval requires PostgreSQL with pgvector", status_code=503, code="retrieval_backend_unavailable")


def _metadata_filters(filters: RetrievalFilters | None) -> list[object]:
    if filters is None:
        return []
    expressions: list[object] = []
    if filters.document_ids:
        expressions.append(Document.id.in_(filters.document_ids))
    if filters.source_types:
        expressions.append(Document.source_type.in_(filters.source_types))
    if filters.content_levels:
        expressions.append(Document.content_level.in_(filters.content_levels))
    if filters.year_from is not None:
        expressions.append(Document.publication_year >= filters.year_from)
    if filters.year_to is not None:
        expressions.append(Document.publication_year <= filters.year_to)
    if filters.doi:
        expressions.append(func.lower(Document.doi) == normalize_doi(filters.doi))
    return expressions


def semantic_search(
    session: Session,
    user_id: UUID,
    query_vector: list[float],
    limit: int,
    project_id: UUID | None = None,
    retrieval_filters: RetrievalFilters | None = None,
) -> list[RankedChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        DocumentChunk.embedding.is_not(None),
    ]
    if project_id is not None:
        filters.append(Document.project_id == project_id)
    filters.extend(_metadata_filters(retrieval_filters))
    rows = session.execute(
        select(DocumentChunk, distance.label("distance"))
        .join(Document)
        .where(*filters)
        .order_by(distance, DocumentChunk.id).limit(limit)
    ).all()
    return [RankedChunk(chunk=row[0], vector_score=1 - float(row[1])) for row in rows]


def keyword_search(
    session: Session,
    user_id: UUID,
    query: str,
    limit: int,
    project_id: UUID | None = None,
    retrieval_filters: RetrievalFilters | None = None,
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
    filters.extend(_metadata_filters(retrieval_filters))
    rows = session.execute(
        select(DocumentChunk, rank.label("rank"))
        .join(Document)
        .where(*filters)
        .order_by(rank.desc(), DocumentChunk.id).limit(limit)
    ).all()
    return [RankedChunk(chunk=row[0], keyword_score=float(row[1])) for row in rows]


def fuse(vector_results: list[RankedChunk], keyword_results: list[RankedChunk], limit: int) -> list[RankedChunk]:
    merged: dict[UUID, RankedChunk] = {}
    scores: dict[UUID, float] = {}
    for result_set, score_name in ((vector_results, "vector_score"), (keyword_results, "keyword_score")):
        for rank, item in enumerate(result_set, start=1):
            key = item.chunk.id
            previous = merged.get(key)
            merged[key] = item if previous is None else replace(previous, **{score_name: getattr(item, score_name)})
            scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank)
    return sorted(merged.values(), key=lambda item: (-scores[item.chunk.id], str(item.chunk.id)))[:limit]


def retrieve(
    session: Session,
    user_id: UUID,
    query: str,
    settings: Settings,
    embeddings: EmbeddingService | None = None,
    *,
    project_id: UUID | None = None,
    filters: RetrievalFilters | None = None,
) -> list[RetrievalCandidate]:
    normalized = query.strip()
    if not normalized:
        raise AppError("A retrieval query is required", status_code=422, code="retrieval_query_required")
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
        filters,
    )
    keyword_results = keyword_search(
        session,
        user_id,
        normalized,
        settings.keyword_top_k,
        project_id,
        filters,
    )
    candidates = fuse(vector_results, keyword_results, settings.hybrid_candidate_k)
    vector_rank = {item.chunk.id: index for index, item in enumerate(vector_results, 1)}
    keyword_rank = {item.chunk.id: index for index, item in enumerate(keyword_results, 1)}
    result: list[RetrievalCandidate] = []
    for item in candidates:
        document = item.chunk.document
        score = (1 / (RRF_K + vector_rank[item.chunk.id]) if item.chunk.id in vector_rank else 0) + (1 / (RRF_K + keyword_rank[item.chunk.id]) if item.chunk.id in keyword_rank else 0)
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
