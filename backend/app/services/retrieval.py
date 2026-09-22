"""PostgreSQL-only, user-scoped hybrid retrieval with reciprocal-rank fusion."""

from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus
from app.models.document import Document, DocumentChunk
from app.schemas.retrieval import RetrievalCandidate
from app.services.embeddings import EmbeddingService, embedding_service_for

RRF_K = 60


@dataclass(frozen=True)
class RankedChunk:
    chunk: DocumentChunk
    vector_score: float | None = None
    keyword_score: float | None = None


def _require_postgres(session: Session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise AppError("Retrieval requires PostgreSQL with pgvector", status_code=503, code="retrieval_backend_unavailable")


def semantic_search(session: Session, user_id: UUID, query_vector: list[float], limit: int) -> list[RankedChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    rows = session.execute(
        select(DocumentChunk, distance.label("distance"))
        .join(Document)
        .where(Document.user_id == user_id, Document.status == DocumentStatus.INDEXED, DocumentChunk.embedding.is_not(None))
        .order_by(distance, DocumentChunk.id).limit(limit)
    ).all()
    return [RankedChunk(chunk=row[0], vector_score=1 - float(row[1])) for row in rows]


def keyword_search(session: Session, user_id: UUID, query: str, limit: int) -> list[RankedChunk]:
    query_expression = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(func.to_tsvector("english", DocumentChunk.text), query_expression)
    rows = session.execute(
        select(DocumentChunk, rank.label("rank"))
        .join(Document)
        .where(Document.user_id == user_id, Document.status == DocumentStatus.INDEXED, func.to_tsvector("english", DocumentChunk.text).op("@@")(query_expression))
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


def retrieve(session: Session, user_id: UUID, query: str, settings: Settings, embeddings: EmbeddingService | None = None) -> list[RetrievalCandidate]:
    _require_postgres(session)
    normalized = query.strip()
    if not normalized:
        raise AppError("A retrieval query is required", status_code=422, code="retrieval_query_required")
    service = embeddings or embedding_service_for(settings)
    vector_results = semantic_search(session, user_id, service.embed_query(normalized), settings.vector_top_k)
    keyword_results = keyword_search(session, user_id, normalized, settings.keyword_top_k)
    candidates = fuse(vector_results, keyword_results, settings.hybrid_candidate_k)
    vector_rank = {item.chunk.id: index for index, item in enumerate(vector_results, 1)}
    keyword_rank = {item.chunk.id: index for index, item in enumerate(keyword_results, 1)}
    result: list[RetrievalCandidate] = []
    for item in candidates:
        document = item.chunk.document
        score = (1 / (RRF_K + vector_rank[item.chunk.id]) if item.chunk.id in vector_rank else 0) + (1 / (RRF_K + keyword_rank[item.chunk.id]) if item.chunk.id in keyword_rank else 0)
        result.append(RetrievalCandidate(chunk_id=item.chunk.id, document_id=document.id, paper_title=document.title or document.name, authors=document.authors, doi=document.doi, page=item.chunk.page, section=item.chunk.section, text=item.chunk.text, vector_score=item.vector_score, keyword_score=item.keyword_score, hybrid_score=score))
    return result
