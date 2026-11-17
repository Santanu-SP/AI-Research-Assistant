"""PostgreSQL hybrid retrieval (pgvector + FTS + RRF) scoped by user and optional research project."""

from dataclasses import dataclass, replace
import math
import re
from uuid import UUID

from sqlalchemy import Text, case, cast, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.documents import DocumentStatus
from app.models.document import Document, DocumentChunk
from app.models.project import ResearchProject
from app.schemas.retrieval import RetrievalCandidate
from app.services.rag.embeddings import EmbeddingService, embedding_service_for
from app.services.research import projects as project_service

# Standard reciprocal-rank fusion constant. A larger k softens the penalty
# for a result that only one of the two lists ranked highly.
RRF_K = 60
FTS_CONFIGURATION = "english"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{2,}")


@dataclass(frozen=True)
class RankedChunk:
    chunk: DocumentChunk
    vector_score: float | None = None
    keyword_score: float | None = None


def preprocess_query(query: str) -> str:
    """Normalize whitespace and strip control characters while preserving terms."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", query)
    return re.sub(r"\s+", " ", cleaned).strip()


# Phrases that point at "the documents" in general. They describe where to
# look, not what to look for, so they only add noise to the search.
_SOURCE_NOUN = (
    r"(?:the\s+|my\s+|our\s+|these\s+|this\s+)?"
    r"(?:(?:source|uploaded|provided|attached|given|supplied)\s+)?"
    r"(?:documents?|docs|files?|sources?|pdfs?|papers?|notes|documentation)"
)
_SOURCE_PREPOSITION = r"(?:in|from|within|inside|according to|based on|as per|using)"
# Only at the end of the question ("... in the source documents?") or at its
# start followed by a comma ("According to the files, ..."), so a real
# question like "What is in the docs folder?" is left alone.
_TRAILING_SOURCE_REFERENCE = re.compile(
    rf"\s+{_SOURCE_PREPOSITION}\s+{_SOURCE_NOUN}\s*(?=[?.!]*$)", re.IGNORECASE
)
_LEADING_SOURCE_REFERENCE = re.compile(
    rf"^{_SOURCE_PREPOSITION}\s+{_SOURCE_NOUN}\s*,\s*", re.IGNORECASE
)


def search_text_for(query: str) -> str:
    """The part of a question worth searching for.

    "How does X work in the source documents?" searches for "How does X
    work?". The full question is still what the model answers.
    """
    normalized = preprocess_query(query)
    stripped = _LEADING_SOURCE_REFERENCE.sub("", normalized)
    stripped = _TRAILING_SOURCE_REFERENCE.sub("", stripped).strip()
    return stripped if _TOKEN_RE.search(stripped) else normalized


def _any_term_tsquery(query: str):
    """Match chunks containing ANY of the query's words, ranked by how many.

    ``websearch_to_tsquery`` joins every word with AND, so a natural question
    ("how will A2A delegation take place in the project") only matches a
    chunk that contains all of those words, which is usually none, and the
    keyword half of hybrid search silently returns nothing. Turning the ANDs
    into ORs keeps quoted phrases and lets ``ts_rank_cd`` rank by overlap.
    Queries using ``-word`` exclusions keep the original AND meaning.
    """
    strict = func.websearch_to_tsquery(FTS_CONFIGURATION, query)
    strict_text = cast(strict, Text)
    return case(
        (func.strpos(strict_text, "!") > 0, strict),
        else_=cast(func.replace(strict_text, " & ", " | "), TSQUERY),
    )


def _require_postgres(session: Session) -> None:
    dialect = None if session.bind is None else session.bind.dialect.name
    if dialect != "postgresql":
        raise AppError(
            "Retrieval requires PostgreSQL with pgvector",
            status_code=503,
            code="retrieval_backend_unavailable",
        )


def _active_project_filter():
    """Exclude chunks whose document lives in an archived project."""
    return or_(
        Document.project_id.is_(None),
        ResearchProject.archived_at.is_(None),
    )


def _scope_filters(project_id: UUID | None, document_ids: list[UUID] | None) -> list:
    """Limit a search to one project and/or a chosen set of documents.

    ``document_ids=None`` means no document limit; an empty list matches
    nothing, so a run whose documents were all deleted finds no evidence
    instead of quietly searching everything.
    """
    filters = []
    if project_id is not None:
        filters.append(Document.project_id == project_id)
    if document_ids is not None:
        filters.append(Document.id.in_(list(document_ids)))
    return filters


def _reciprocal_rank(rank: int, rrf_k: int = RRF_K) -> float:
    return 1 / (rrf_k + rank)


def semantic_search(
    session: Session,
    user_id: UUID,
    query_vector: list[float],
    limit: int,
    project_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
) -> list[RankedChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        DocumentChunk.embedding.is_not(None),
        _active_project_filter(),
    ]
    filters.extend(_scope_filters(project_id, document_ids))
    rows = session.execute(
        select(DocumentChunk, distance.label("distance"))
        .options(joinedload(DocumentChunk.document))
        .join(Document)
        .outerjoin(ResearchProject, ResearchProject.id == Document.project_id)
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
    document_ids: list[UUID] | None = None,
) -> list[RankedChunk]:
    query_expression = _any_term_tsquery(query)
    rank = func.ts_rank_cd(DocumentChunk.search_vector, query_expression)
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        DocumentChunk.search_vector.op("@@")(query_expression),
        _active_project_filter(),
    ]
    filters.extend(_scope_filters(project_id, document_ids))
    rows = session.execute(
        select(DocumentChunk, rank.label("rank"))
        .options(joinedload(DocumentChunk.document))
        .join(Document)
        .outerjoin(ResearchProject, ResearchProject.id == Document.project_id)
        .where(*filters)
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(limit)
    ).all()
    return [
        RankedChunk(chunk=row[0], keyword_score=float(row[1]))
        for row in rows
    ]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(float(a) * float(a) for a in vec_a))
    norm_b = math.sqrt(sum(float(b) * float(b) for b in vec_b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    return dot / (norm_a * norm_b)


def _sqlite_hybrid_search(
    session: Session,
    user_id: UUID,
    query: str,
    query_vector: list[float],
    vector_limit: int,
    keyword_limit: int,
    project_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
) -> tuple[list[RankedChunk], list[RankedChunk]]:
    filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        _active_project_filter(),
    ]
    filters.extend(_scope_filters(project_id, document_ids))
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .options(joinedload(DocumentChunk.document))
            .join(Document)
            .outerjoin(ResearchProject, ResearchProject.id == Document.project_id)
            .where(*filters)
        ).all()
    )
    vector_candidates: list[RankedChunk] = []
    for chunk in chunks:
        if chunk.embedding is not None:
            sim = _cosine_similarity(list(chunk.embedding), query_vector)
            vector_candidates.append(RankedChunk(chunk=chunk, vector_score=sim))
    vector_candidates.sort(key=lambda item: (-float(item.vector_score or 0.0), str(item.chunk.id)))
    vector_results = vector_candidates[:vector_limit]

    query_terms = [term.lower() for term in _TOKEN_RE.findall(query)]
    keyword_candidates: list[RankedChunk] = []
    if query_terms:
        for chunk in chunks:
            haystack = f"{chunk.section or ''} {chunk.text}".lower()
            matched = sum(1 for term in query_terms if term in haystack)
            if matched > 0:
                score = matched / len(query_terms)
                keyword_candidates.append(RankedChunk(chunk=chunk, keyword_score=score))
    keyword_candidates.sort(key=lambda item: (-float(item.keyword_score or 0.0), str(item.chunk.id)))
    keyword_results = keyword_candidates[:keyword_limit]
    return vector_results, keyword_results


def fuse(
    vector_results: list[RankedChunk],
    keyword_results: list[RankedChunk],
    limit: int,
    *,
    rrf_k: int = RRF_K,
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
            scores[chunk_id] = scores.get(chunk_id, 0.0) + _reciprocal_rank(rank, rrf_k)

    ranked = sorted(
        merged.values(),
        key=lambda item: (-scores[item.chunk.id], str(item.chunk.id)),
    )
    return ranked[:limit]


def _hybrid_score(
    chunk_id: UUID,
    vector_ranks: dict[UUID, int],
    keyword_ranks: dict[UUID, int],
    *,
    rrf_k: int = RRF_K,
) -> float:
    score = 0.0
    if chunk_id in vector_ranks:
        score += _reciprocal_rank(vector_ranks[chunk_id], rrf_k)
    if chunk_id in keyword_ranks:
        score += _reciprocal_rank(keyword_ranks[chunk_id], rrf_k)
    return score


def _postgres_hybrid_search(
    session: Session,
    user_id: UUID,
    query: str,
    query_vector: list[float],
    vector_limit: int,
    keyword_limit: int,
    project_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
) -> tuple[list[RankedChunk], list[RankedChunk]]:
    """Fetch vector and FTS top-k candidates in a single PostgreSQL round-trip."""
    base_filters = [
        Document.user_id == user_id,
        Document.status == DocumentStatus.INDEXED,
        _active_project_filter(),
    ]
    base_filters.extend(_scope_filters(project_id, document_ids))

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    vec_q = (
        select(
            DocumentChunk.id.label("chunk_id"),
            literal(1).label("kind"),
            (1.0 - distance).label("score"),
        )
        .join(Document)
        .outerjoin(ResearchProject, ResearchProject.id == Document.project_id)
        .where(*base_filters, DocumentChunk.embedding.is_not(None))
        .order_by(distance, DocumentChunk.id)
        .limit(vector_limit)
    )

    query_expression = _any_term_tsquery(query)
    ts_rank = func.ts_rank_cd(DocumentChunk.search_vector, query_expression)
    kw_q = (
        select(
            DocumentChunk.id.label("chunk_id"),
            literal(2).label("kind"),
            ts_rank.label("score"),
        )
        .join(Document)
        .outerjoin(ResearchProject, ResearchProject.id == Document.project_id)
        .where(*base_filters, DocumentChunk.search_vector.op("@@")(query_expression))
        .order_by(ts_rank.desc(), DocumentChunk.id)
        .limit(keyword_limit)
    )

    combined = union_all(vec_q, kw_q).alias("hybrid_hits")
    rows = session.execute(
        select(
            DocumentChunk,
            combined.c.kind,
            combined.c.score,
        )
        .options(joinedload(DocumentChunk.document))
        .join(combined, combined.c.chunk_id == DocumentChunk.id)
    ).all()

    vector_results: list[RankedChunk] = []
    keyword_results: list[RankedChunk] = []
    for chunk, kind, score in rows:
        if kind == 1:
            vector_results.append(RankedChunk(chunk=chunk, vector_score=float(score)))
        else:
            keyword_results.append(RankedChunk(chunk=chunk, keyword_score=float(score)))
    vector_results.sort(key=lambda item: (-float(item.vector_score or 0.0), item.chunk.id))
    keyword_results.sort(key=lambda item: (-float(item.keyword_score or 0.0), item.chunk.id))
    return vector_results, keyword_results


def retrieve(
    session: Session,
    user_id: UUID,
    query: str,
    settings: Settings,
    embeddings: EmbeddingService | None = None,
    *,
    project_id: UUID | None = None,
    document_ids: list[UUID] | None = None,
) -> list[RetrievalCandidate]:
    normalized = preprocess_query(query)
    if not normalized:
        raise AppError(
            "A retrieval query is required",
            status_code=422,
            code="retrieval_query_required",
        )
    normalized = search_text_for(normalized)
    if project_id is not None:
        project_service.get_project(session, project_id, user_id)
    if document_ids is not None and not document_ids:
        return []

    dialect = None if session.bind is None else session.bind.dialect.name
    if dialect != "postgresql" and not settings.allow_sqlite_retrieval_fallback:
        _require_postgres(session)

    service = embeddings or embedding_service_for(settings)
    query_vector = service.embed_query(normalized)

    if dialect == "postgresql":
        vector_results, keyword_results = _postgres_hybrid_search(
            session,
            user_id,
            normalized,
            query_vector,
            settings.vector_top_k,
            settings.keyword_top_k,
            project_id,
            document_ids,
        )
    else:
        vector_results, keyword_results = _sqlite_hybrid_search(
            session,
            user_id,
            normalized,
            query_vector,
            settings.vector_top_k,
            settings.keyword_top_k,
            project_id,
            document_ids,
        )

    rrf_k = getattr(settings, "rrf_k", RRF_K)
    candidates = fuse(
        vector_results,
        keyword_results,
        settings.hybrid_candidate_k,
        rrf_k=rrf_k,
    )
    vector_ranks = {
        item.chunk.id: index for index, item in enumerate(vector_results, start=1)
    }
    keyword_ranks = {
        item.chunk.id: index for index, item in enumerate(keyword_results, start=1)
    }

    result: list[RetrievalCandidate] = []
    for item in candidates:
        document = item.chunk.document
        canonical_meta = document.canonical_metadata or {}
        raw_publisher = canonical_meta.get("publisher") if isinstance(canonical_meta, dict) else None
        publisher = str(raw_publisher).strip() if raw_publisher else None
        score = _hybrid_score(item.chunk.id, vector_ranks, keyword_ranks, rrf_k=rrf_k)
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
                url=document.source_url,
                publisher=publisher,
                year=document.publication_year,
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
