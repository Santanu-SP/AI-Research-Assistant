"""Orchestration for the authenticated grounded local RAG request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
import re
from time import monotonic
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.realtime_bus import project_room, publish_realtime_event, research_room
from app.core.time import utc_now
from app.domain.collaboration import CollaboratorRole
from app.domain.documents import SourceType as DocumentSourceType
from app.domain.reports import SourceType
from app.domain.research import ResearchDepth, ResearchStatus
from app.domain.states import ProjectStatus
from app.schemas.rag import (
    EvidenceItem,
    ReportFollowupRequest,
    ResearchQueryRequest,
    ResearchQueryResponse,
    ResearchRetryRequest,
)
from app.schemas.reports import ReportFollowupCreateResponse, ResearchReportCreate
from app.schemas.research import ResearchCreate
from app.services.rag import retrieval
from app.services.rag.citations import CitationValidator, SOURCE_REFERENCE
from app.services.rag.evidence import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    EvidenceBuilder,
    evidence_is_sufficient,
)
from app.services.rag.generation import GenerationService, generation_service_for
from app.services.rag.reranking import RerankerService, reranker_service_for
from app.models.document import Document
from app.models.report import ReportFollowup, ResearchReport, Source
from app.models.research import Research
from app.services.collaboration.access import actor_for_user, require_research_access
from app.services.collaboration.service import attach_research_collab_metadata
from app.services.jobs import queue as job_queue
from app.services.observability.telemetry import estimate_cost_usd, record_telemetry_event
from app.services.observability.usage import (
    CREDIT_UNITS_FOLLOWUP,
    acquire_run_quota_policy,
    ensure_research_shared_quota,
    record_model_usage,
    release_research_shared_quota,
    settle_research_shared_quota,
)
from app.services.research import reports
from app.services.research import runs as research
from app.services.research.titles import MAX_CHAT_TITLE_WORDS, normalize_short_title

logger = logging.getLogger(__name__)

_COMPLEX_QUERY_RE = re.compile(
    r"\b(?:"
    r"compare|contrast|difference|differences|versus|vs\.?|relationship|"
    r"trade[- ]?off|evaluate|analyze|analyse|synthesize|synthesise|"
    r"summarize|summarise|summary|explain|explanation|list|overview|"
    r"detail|details|detailed|finding|findings|mechanism|mechanisms|"
    r"describe|outline|discuss|elaborate|implication|implications|"
    r"comprehensive|thorough|critique|limitation|limitations|methodology|"
    r"methodologies|architecture|why does|why do|why is|how does|how do|"
    r"step by step|timeline|"
    r"across (?:the )?(?:papers|documents|sources|studies|chapters)|"
    r"all (?:papers|documents|sources|studies)"
    r")\b",
    re.IGNORECASE,
)


def is_simple_question(question: str) -> bool:
    """Return True for short, single-intent factual questions."""
    normalized = " ".join(question.strip().split())
    if not normalized:
        return False
    if "\n" in question.strip() or ";" in normalized or normalized.count("?") > 1:
        return False
    if len(normalized.split()) > 12:
        return False
    return _COMPLEX_QUERY_RE.search(normalized) is None


@dataclass(frozen=True)
class ResearchExecutionProfile:
    """Depth- and complexity-aware runtime budgets derived from Settings."""

    mode: str
    settings: Settings
    provider_timeout_seconds: float | None = None
    primary_timeout_seconds: float | None = None
    allow_sticky_fallback: bool = True


def _depth_timeout_controls(
    depth: ResearchDepth,
    settings: Settings,
) -> tuple[float, float, bool]:
    if depth == ResearchDepth.QUICK:
        return (
            settings.llm_quick_timeout_seconds,
            min(settings.llm_quick_timeout_seconds, settings.gemini_primary_timeout_seconds),
            True,
        )
    if depth == ResearchDepth.DEEP:
        return (
            settings.llm_deep_timeout_seconds,
            settings.llm_deep_timeout_seconds,
            False,
        )
    return (
        settings.llm_provider_timeout_seconds,
        settings.gemini_primary_timeout_seconds,
        True,
    )


def resolve_execution_profile(
    question: str,
    depth: ResearchDepth | str,
    settings: Settings,
) -> ResearchExecutionProfile:
    """Tune retrieval top-k, reranker backend, timeouts, and generation tokens to query difficulty."""
    try:
        resolved_depth = ResearchDepth(depth)
    except ValueError:
        resolved_depth = ResearchDepth.STANDARD

    provider_timeout, primary_timeout, allow_sticky = _depth_timeout_controls(
        resolved_depth, settings
    )

    if not settings.adaptive_fast_path_enabled:
        return ResearchExecutionProfile(
            mode=resolved_depth.value,
            settings=settings,
            provider_timeout_seconds=provider_timeout,
            primary_timeout_seconds=primary_timeout,
            allow_sticky_fallback=allow_sticky,
        )

    if resolved_depth == ResearchDepth.QUICK:
        return ResearchExecutionProfile(
            mode="quick",
            settings=settings.model_copy(
                update={
                    "vector_top_k": min(settings.vector_top_k, 10),
                    "keyword_top_k": min(settings.keyword_top_k, 10),
                    "hybrid_candidate_k": min(settings.hybrid_candidate_k, 10),
                    "reranker_provider": "lexical",
                    "final_context_k": min(settings.final_context_k, 4),
                    "generation_max_new_tokens": min(settings.generation_max_new_tokens, 384),
                }
            ),
            provider_timeout_seconds=provider_timeout,
            primary_timeout_seconds=primary_timeout,
            allow_sticky_fallback=allow_sticky,
        )

    if resolved_depth == ResearchDepth.STANDARD and is_simple_question(question):
        return ResearchExecutionProfile(
            mode="fast_standard",
            settings=settings.model_copy(
                update={
                    "vector_top_k": min(settings.vector_top_k, 12),
                    "keyword_top_k": min(settings.keyword_top_k, 12),
                    "hybrid_candidate_k": min(settings.hybrid_candidate_k, 12),
                    "reranker_provider": "lexical",
                    "final_context_k": min(settings.final_context_k, 5),
                    "generation_max_new_tokens": min(settings.generation_max_new_tokens, 448),
                }
            ),
            provider_timeout_seconds=provider_timeout,
            primary_timeout_seconds=primary_timeout,
            allow_sticky_fallback=allow_sticky,
        )

    if resolved_depth == ResearchDepth.STANDARD:
        return ResearchExecutionProfile(
            mode="standard",
            settings=settings,
            provider_timeout_seconds=provider_timeout,
            primary_timeout_seconds=primary_timeout,
            allow_sticky_fallback=allow_sticky,
        )

    # Deep reads more: chunks are often short (one heading each), so a wider
    # pool and a few more evidence blocks cost little and catch the states,
    # failure cases and endpoints that sit in separate sections.
    return ResearchExecutionProfile(
        mode="deep",
        settings=settings.model_copy(
            update={
                "hybrid_candidate_k": max(settings.hybrid_candidate_k, 30),
                "final_context_k": max(settings.final_context_k, 12),
                "evidence_char_budget": max(settings.evidence_char_budget, 12000),
                "evidence_max_items": max(settings.evidence_max_items, 20),
                "generation_max_new_tokens": max(settings.generation_max_new_tokens, 1024),
            }
        ),
        provider_timeout_seconds=provider_timeout,
        primary_timeout_seconds=primary_timeout,
        allow_sticky_fallback=allow_sticky,
    )


def build_evidence(ranked, settings: Settings, mode: str):
    """Pick the evidence blocks for the prompt.

    Quick and fast paths keep their small fixed count. Standard and deep top
    up with further relevant chunks while the evidence is still short.
    """
    if mode in ("standard", "deep"):
        return EvidenceBuilder().build(
            ranked,
            limit=settings.final_context_k,
            char_budget=settings.evidence_char_budget,
            max_items=settings.evidence_max_items,
            min_extra_score=settings.reranker_min_score,
        )
    return EvidenceBuilder().build(ranked, limit=settings.final_context_k)


def _plain_answer(answer: str) -> str:
    without_references = SOURCE_REFERENCE.sub("", answer)
    without_reference_spacing = re.sub(
        r"[ \t]+([,.;:!?])", r"\1", without_references
    )
    return re.sub(r" {2,}", " ", without_reference_spacing).strip()


def _report_source_type(item) -> SourceType:
    doc_source = getattr(item, "source_type", None)
    publisher = (getattr(item, "publisher", None) or "").lower()
    if "arxiv" in publisher:
        return SourceType.PREPRINT
    if doc_source is not None:
        raw = str(getattr(doc_source, "value", doc_source)).lower()
        if raw in {"openalex", "crossref", "doi"}:
            return SourceType.PEER_REVIEWED
        if raw == "web_page":
            return SourceType.INSTITUTIONAL
    return SourceType.TECHNICAL_REPORT


def _truncate_str(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned[:limit] or None


def _report_payload(
    *,
    research_id: UUID,
    title: str,
    answer: str,
    citations,
    evidence,
) -> ResearchReportCreate:
    evidence_by_id = {item.source_id: item for item in evidence}
    source_payloads = []
    citation_payloads = []
    for position, citation in enumerate(citations):
        source_number = int(citation.citation_id[1:])
        source_uuid = uuid5(research_id, citation.citation_id)
        item = evidence_by_id[citation.citation_id]
        raw_authors = [
            name.strip()[:200]
            for name in (citation.authors or [])[:50]
            if isinstance(name, str) and name.strip()
        ]
        raw_year = getattr(item, "year", None)
        safe_year = raw_year if isinstance(raw_year, int) and 1000 <= raw_year <= 9999 else None
        raw_url = getattr(citation, "url", None) or (
            f"https://doi.org/{citation.doi}" if citation.doi else None
        )
        source_payloads.append(
            {
                "id": source_uuid,
                "number": source_number,
                "title": _truncate_str(citation.paper_title, 500),
                "publisher": _truncate_str(getattr(item, "publisher", None), 200),
                "authors": raw_authors,
                "year": safe_year,
                "url": _truncate_str(raw_url, 2048),
                "sourceType": _report_source_type(item),
                "relevantExcerpt": citation.excerpt,
                "doi": _truncate_str(citation.doi, 255),
                "documentId": citation.document_id,
                "chunkId": citation.chunk_id,
                "page": citation.page,
                "section": _truncate_str(citation.section, 500),
                "rerankScore": item.rerank_score,
            }
        )
        citation_payloads.append({"sourceId": source_uuid, "position": position})

    # Keep the [S1] markers: the report page turns them into clickable
    # source chips next to the sentence they support.
    display_answer = answer.strip()
    reading_minutes = max(1, len(_plain_answer(answer).split()) // 200 + 1)
    return ResearchReportCreate(
        title=title,
        summary=display_answer,
        dossier_ref=f"LOCAL RAG · {str(research_id)[:8].upper()}",
        reading_time_minutes=reading_minutes,
        sources=source_payloads,
        sections=[
            {
                "heading": "Grounded answer",
                "content": display_answer,
                "position": 0,
                "citations": citation_payloads,
            }
        ],
    )


def _wants_discovery(payload: ResearchQueryRequest) -> bool:
    return payload.auto_discover and not payload.document_ids


def _select_diverse_discovery_candidates(
    items: list,
    *,
    scope: str,
) -> list:
    """Interleave news, encyclopedia, and scholarly hits when ``scope == 'all'``."""
    if scope != "all" or len(items) <= 1:
        return list(items)

    news_items = [
        item
        for item in items
        if item.provider == "wikipedia" and item.publisher and item.publisher != "Wikipedia"
    ]
    wiki_items = [
        item
        for item in items
        if item.provider == "wikipedia" and (not item.publisher or item.publisher == "Wikipedia")
    ]
    scholarly_items = [item for item in items if item.provider != "wikipedia"]

    ordered: list = []
    seen_ids: set[str] = set()
    max_len = max(len(news_items), len(wiki_items), len(scholarly_items))
    for index in range(max_len):
        for bucket in (news_items, wiki_items, scholarly_items):
            if index < len(bucket):
                cand = bucket[index]
                if cand.candidate_id not in seen_ids:
                    seen_ids.add(cand.candidate_id)
                    ordered.append(cand)
    for cand in items:
        if cand.candidate_id not in seen_ids:
            seen_ids.add(cand.candidate_id)
            ordered.append(cand)
    return ordered


def discover_documents(
    session: Session,
    user_id: UUID,
    *,
    query: str,
    scope: str,
    project_id: UUID | None,
    storage,
    settings: Settings,
) -> list[UUID]:
    """Search the trusted providers, import the best diverse matches and return their ids."""
    from app.services.discovery import service as discovery_service

    search_result = discovery_service.search_and_annotate(
        session,
        user_id=user_id,
        query=query,
        scope=scope,
        limit=settings.discovery_max_results,
        project_id=project_id,
        settings=settings,
    )
    if not search_result.items:
        raise AppError(
            "No trustworthy external sources were found for this question.",
            status_code=422,
            code="no_discoverable_sources",
        )

    ordered = _select_diverse_discovery_candidates(search_result.items, scope=scope)
    target_count = (
        max(settings.discovery_auto_import_limit, 4)
        if scope == "all"
        else settings.discovery_auto_import_limit
    )

    doc_ids: list[UUID] = []
    seen_doc_ids: set[UUID] = set()
    # First batch up to target_count, then fall back through remaining ranked items if any fail.
    batches = [ordered[:target_count]] + [[item] for item in ordered[target_count:]]
    for batch in batches:
        if not batch or len(doc_ids) >= target_count:
            break
        imported = discovery_service.import_discovered_sources(
            session,
            batch,
            storage=storage,
            settings=settings,
            user_id=user_id,
            project_id=project_id,
            fetch_full_text=True,
        )
        for doc in imported.documents:
            if doc.id not in seen_doc_ids:
                seen_doc_ids.add(doc.id)
                doc_ids.append(doc.id)

    if not doc_ids:
        raise AppError(
            "Found external references could not be extracted into readable evidence.",
            status_code=422,
            code="no_discoverable_sources",
        )
    return doc_ids[:target_count]


def prepare_discovered_documents_if_requested(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    storage,
    settings: Settings,
) -> ResearchQueryRequest:
    """When ``auto_discover`` is opted in with no picked documents, discover & ingest curated sources."""
    if not _wants_discovery(payload):
        return payload
    doc_ids = discover_documents(
        session,
        user_id,
        query=payload.query,
        scope=payload.discovery_scope,
        project_id=payload.project_id,
        storage=storage,
        settings=settings,
    )
    return payload.model_copy(update={"document_ids": doc_ids})


def _ensure_discovery_enabled(payload: ResearchQueryRequest, settings: Settings) -> None:
    if _wants_discovery(payload) and not settings.discovery_enabled:
        raise AppError(
            "Controlled discovery is disabled in server configuration",
            status_code=503,
            code="discovery_disabled",
        )


def _discover_sources_for_run(
    session: Session,
    record: Research,
    user_id: UUID,
    settings: Settings,
) -> None:
    """Find, import and attach sources for a run started with auto-discovery.

    Runs inside the background job so starting the research never waits on
    the providers, PDF downloads or parsing.
    """
    from app.services.documents.storage import storage_for_settings

    research.advance_research_progress(
        session,
        record.id,
        project_status=ProjectStatus.PAPERS_DISCOVERED,
        commit=True,
    )
    doc_ids = discover_documents(
        session,
        user_id,
        query=record.question,
        scope=record.discovery_scope or "all",
        project_id=record.project_id,
        storage=storage_for_settings(settings),
        settings=settings,
    )
    documents = list(session.scalars(select(Document).where(Document.id.in_(doc_ids))))
    order = {doc_id: index for index, doc_id in enumerate(doc_ids)}
    documents.sort(key=lambda doc: order[doc.id])
    record = research.get_research(session, record.id, user_id)
    record.documents_scoped = True
    record.attached_documents = documents
    session.add(record)
    research.advance_research_progress(
        session,
        record.id,
        project_status=ProjectStatus.PROCESSING,
        commit=True,
    )


def run_query(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    settings: Settings,
    *,
    reranker: RerankerService | None = None,
    generator: GenerationService | None = None,
) -> ResearchQueryResponse:
    """Create a research run and answer it within the current request."""
    duplicate = find_recent_duplicate(session, user_id, payload)
    if duplicate is not None:
        # The same question was just sent (a double click or a resent
        # request). Point the client at the run that is already going
        # instead of starting a second one.
        raise AppError(
            "This question is already being researched",
            status_code=409,
            code="research_already_running",
            details={"researchId": str(duplicate.id)},
        )
    record = _create_started_record(session, user_id, payload, settings)
    try:
        return execute_research(
            session,
            record.id,
            user_id,
            settings,
            reranker=reranker,
            generator=generator,
            commit_intermediate=False,
        )
    except AppError as exc:
        # Let the client offer "Try again" on this same run instead of
        # creating a new one.
        exc.details = {**(exc.details or {}), "researchId": str(record.id)}
        raise


def queue_query(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    settings: Settings | None = None,
) -> Research:
    """Create a research run and leave the work to the background worker.

    With ``auto_discover`` and no picked documents, the worker finds and
    imports the sources itself before answering.
    """
    _ensure_discovery_enabled(payload, settings or get_settings())
    duplicate = find_recent_duplicate(session, user_id, payload)
    if duplicate is not None:
        return duplicate
    record = _create_started_record(session, user_id, payload, settings)
    job_queue.enqueue(session, job_queue.RUN_RESEARCH, record.id)
    loaded = research.get_research(session, record.id, user_id)
    attach_research_collab_metadata(session, [loaded], user_id)
    return loaded


# A repeat of the same question inside this window is treated as the same
# submission (double clicks, a resent request after a slow network).
DUPLICATE_SUBMIT_WINDOW_SECONDS = 15


def find_recent_duplicate(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
) -> Research | None:
    normalized_query = payload.query.strip()
    if not normalized_query:
        return None
    cutoff = utc_now() - timedelta(seconds=DUPLICATE_SUBMIT_WINDOW_SECONDS)
    filters = [
        Research.user_id == user_id,
        Research.question == normalized_query,
        Research.research_depth == payload.research_depth,
        Research.created_at >= cutoff,
        Research.archived_at.is_(None),
        Research.status.in_((ResearchStatus.DRAFT, ResearchStatus.RESEARCHING)),
    ]
    if payload.project_id is None:
        filters.append(Research.project_id.is_(None))
    else:
        filters.append(Research.project_id == payload.project_id)
    # Only the same question over the same documents counts as a repeat;
    # asking it again about other files is a new research.
    wanted = _requested_document_scope(payload)
    recent = session.scalars(
        select(Research).where(*filters).order_by(Research.created_at.desc()).limit(5)
    )
    for candidate in recent:
        if _document_scope(candidate) == wanted:
            return candidate
    return None


def scoped_document_ids(record: Research) -> list[UUID] | None:
    """The documents a run may read, or None when it isn't limited to chosen ones."""
    return list(record.document_ids) if record.documents_scoped else None


def _document_scope(record: Research) -> frozenset[UUID] | None:
    ids = scoped_document_ids(record)
    return None if ids is None else frozenset(ids)


def _requested_document_scope(payload: ResearchQueryRequest) -> frozenset[UUID] | None:
    if not payload.document_ids:
        # Not sent, or empty inside a project: the run won't be limited.
        return None
    return frozenset(payload.document_ids)


def _apply_run_options(
    session: Session,
    record: Research,
    user_id: UUID,
    *,
    preferred_provider: str | None,
    model_override: str | None,
    local_fallback_enabled: bool | None,
    settings: Settings,
) -> tuple[bool, object | None]:
    """Store the model choices on the run and reserve shared quota for it."""
    from app.services.auth import api_keys as api_key_service

    pref_provider = preferred_provider.strip().lower() if preferred_provider else None
    override = model_override.strip() if model_override else None
    local_fallback = (
        local_fallback_enabled
        if local_fallback_enabled is not None
        else api_key_service.get_local_fallback_pref(session, user_id)
    )
    user_byok_keys = api_key_service.get_decrypted_user_api_keys(session, user_id, settings)
    allow_shared, quota_reserved, quota_date, _ = acquire_run_quota_policy(
        session,
        user_id=user_id,
        preferred_provider=pref_provider,
        user_byok_providers=set(user_byok_keys.keys()),
        local_enabled=bool(local_fallback),
        research_id=record.id,
        settings=settings,
    )
    record.preferred_provider = pref_provider or None
    record.model_override = override or None
    record.local_fallback_enabled = local_fallback
    record.allow_shared_providers = allow_shared
    record.shared_quota_reserved = quota_reserved
    record.shared_quota_date = quota_date
    return bool(quota_reserved), quota_date


def _release_on_error(
    session: Session,
    user_id: UUID,
    reserved: bool,
    quota_date,
    research_id: UUID | None = None,
) -> None:
    if reserved and quota_date is not None:
        session.rollback()
        if research_id is not None:
            release_research_shared_quota(session, research_id, commit=True)
            return
        from app.services.observability.usage import release_shared_quota_slot

        release_shared_quota_slot(session, user_id=user_id, usage_date=quota_date, commit=True)


def _create_started_record(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    settings: Settings | None = None,
) -> Research:
    normalized_query = payload.query.strip()
    if not normalized_query:
        raise AppError(
            "A research question is required",
            status_code=422,
            code="research_query_required",
        )
    runtime_settings = settings or get_settings()
    reserved, quota_date = False, None
    record = None
    try:
        record = research.create_research(
            session,
            ResearchCreate(
                question=normalized_query,
                project_id=payload.project_id,
                document_ids=payload.document_ids,
                research_depth=payload.research_depth,
            ),
            user_id,
        )
        reserved, quota_date = _apply_run_options(
            session,
            record,
            user_id,
            preferred_provider=payload.preferred_provider,
            model_override=payload.model_override,
            local_fallback_enabled=payload.local_fallback_enabled,
            settings=runtime_settings,
        )
        if _wants_discovery(payload):
            record.discovery_scope = payload.discovery_scope
        session.add(record)
        research.start_research(session, record.id)
    except Exception:
        _release_on_error(session, user_id, reserved, quota_date, record.id if record else None)
        raise
    return record


def _first_set(*values: bool | None) -> bool | None:
    return next((value for value in values if value is not None), None)


def retry_research(
    session: Session,
    user_id: UUID,
    research_id: UUID,
    payload: ResearchRetryRequest,
    settings: Settings | None = None,
) -> Research:
    """Run a failed research item again in place, so history keeps one entry.

    An edited question replaces the old one on the same record. The work is
    queued for the background worker like any other run.
    """
    from app.services.auth import api_keys as api_key_service

    runtime_settings = settings or get_settings()
    record = research.get_research(
        session, research_id, user_id, min_role=CollaboratorRole.EDITOR
    )
    if record.status != ResearchStatus.FAILED:
        raise AppError(
            "Only research that stopped before finishing can be run again",
            status_code=409,
            code="research_not_retryable",
        )
    if job_queue.has_active_job(session, job_queue.RUN_RESEARCH, record.id):
        raise AppError(
            "This research is already running again",
            status_code=409,
            code="research_already_running",
            details={"researchId": str(record.id)},
        )
    new_question = payload.query.strip() if payload.query else None
    if new_question and new_question != record.question:
        if research.is_auto_generated_title(record.title, record.question):
            record.title = research.build_fallback_title(new_question)
        record.question = new_question
    elif (
        record.title == research.legacy_fallback_title(record.question)
        and len(record.title.split()) > MAX_CHAT_TITLE_WORDS
    ):
        record.title = research.build_fallback_title(record.question)
    if payload.research_depth is not None:
        record.research_depth = payload.research_depth
    reserved, quota_date = False, None
    try:
        reserved, quota_date = _apply_run_options(
            session,
            record,
            user_id,
            preferred_provider=(
                payload.preferred_provider
                if "preferred_provider" in payload.model_fields_set
                else record.preferred_provider
            ),
            model_override=(
                payload.model_override
                if "model_override" in payload.model_fields_set
                else record.model_override
            ),
            # A local model switched on since the failure (for example from
            # the Models menu) should be used by the next attempt.
            local_fallback_enabled=_first_set(
                payload.local_fallback_enabled,
                api_key_service.get_local_fallback_pref(session, user_id),
                record.local_fallback_enabled,
            ),
            settings=runtime_settings,
        )
        record.failure_provider = None
        record.failure_model = None
        record.failure_type = None
        research.restart_research(session, record.id, commit=False)
        job_queue.enqueue(session, job_queue.RUN_RESEARCH, record.id, commit=False)
        session.commit()
    except Exception:
        _release_on_error(session, user_id, reserved, quota_date, record.id)
        raise
    reloaded = research.get_research(session, record.id, user_id)
    attach_research_collab_metadata(session, [reloaded], user_id)
    research.broadcast_research_event(
        session, reloaded, "research.started", actor_id=user_id
    )
    return reloaded


_MODEL_ERROR_CODES = {
    "generation_unavailable",
    "generation_invalid_request",
    "generation_timeout",
    "generation_empty_response",
}


def _remember_model_failure(
    session: Session,
    record: Research,
    exc: AppError,
    user_id: UUID,
    settings: Settings,
) -> None:
    """Store why the model failed on the run and log each failed attempt.

    The run keeps the first failed attempt (the model the user asked for, or
    the first in the fallback order), which is the one worth explaining.
    """
    if exc.code not in _MODEL_ERROR_CODES:
        return
    raw = (exc.details or {}).get("modelFailures")
    failures = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if not failures and exc.code == "generation_timeout":
        failures = [{"provider": "ollama", "model": "", "errorType": "timeout"}]
    first = failures[0] if failures else None
    record.failure_provider = str(first.get("provider") or "")[:64] or None if first else None
    record.failure_model = str(first.get("model") or "")[:160] or None if first else None
    record.failure_type = str(first.get("errorType") or "other")[:32] if first else "other"
    session.add(record)
    if not settings.telemetry_enabled:
        return
    for item in failures:
        record_telemetry_event(
            session,
            event_type="llm_generation",
            operation="research_answer",
            provider=str(item.get("provider") or "") or None,
            model=str(item.get("model") or "") or None,
            status="error",
            error_code=str(item.get("errorType") or "other"),
            user_id=user_id,
            metadata={
                "used_byok": bool(item.get("usedByok")),
                "depth": str(record.research_depth),
                "research_id": str(record.id),
            },
            settings=settings,
            commit=False,
        )


def execute_research(
    session: Session,
    research_id: UUID,
    user_id: UUID,
    settings: Settings,
    *,
    reranker: RerankerService | None = None,
    generator: GenerationService | None = None,
    commit_intermediate: bool = True,
) -> ResearchQueryResponse:
    """Run retrieval, reranking, and grounded generation for one research run."""
    started_at = monotonic()
    record = research.get_research(session, research_id, user_id)
    normalized_query = record.question.strip()
    profile = resolve_execution_profile(
        normalized_query,
        record.research_depth,
        settings,
    )
    runtime_settings = profile.settings
    try:
        if record.discovery_scope and not record.documents_scoped:
            _discover_sources_for_run(session, record, user_id, settings)
            record = research.get_research(session, research_id, user_id)
        doc_scope = scoped_document_ids(record)
        candidates = retrieval.retrieve(
            session,
            user_id,
            normalized_query,
            runtime_settings,
            project_id=record.project_id,
            document_ids=doc_scope,
        )
        if candidates:
            ranked = (reranker or reranker_service_for(runtime_settings)).rerank(
                normalized_query, candidates
            )
        else:
            ranked = []
        evidence = build_evidence(ranked, runtime_settings, profile.mode)
        insufficient = not evidence_is_sufficient(
            evidence,
            minimum_count=runtime_settings.minimum_evidence_count,
            minimum_relevance=runtime_settings.reranker_min_score,
        )
        research.advance_research_progress(
            session,
            record.id,
            project_status=(
                ProjectStatus.RESEARCH_READY
                if insufficient
                else ProjectStatus.REVIEW_READY
            ),
            sources_discovered=len(candidates),
            sources_reviewed=len(evidence),
            documents_found=len({item.document_id for item in candidates}),
            commit=commit_intermediate,
        )
        if not insufficient:
            active_generator = generator or generation_service_for(runtime_settings)
            from app.services.auth import api_keys as api_key_service

            pref_provider = record.preferred_provider
            model_override = record.model_override
            local_fallback = record.local_fallback_enabled
            if local_fallback is None:
                local_fallback = api_key_service.get_local_fallback_pref(session, user_id)

            user_keys = api_key_service.get_decrypted_user_api_keys(
                session, user_id, runtime_settings
            )
            user_models = api_key_service.get_user_provider_models(session, user_id)

            def _before_shared_attempt(attempted_provider: str) -> bool:
                return ensure_research_shared_quota(
                    session,
                    research_id=record.id,
                    user_id=user_id,
                    provider=attempted_provider,
                    settings=runtime_settings,
                    commit=True,
                )

            gen_kwargs: dict[str, object] = {
                "user_api_keys": user_keys or None,
                "preferred_provider": (str(pref_provider) if pref_provider else None),
                "model_override": (str(model_override) if model_override else None),
                "local_fallback_enabled": (
                    bool(local_fallback) if local_fallback is not None else None
                ),
                "allow_shared_providers": bool(record.allow_shared_providers),
                "before_shared_attempt": _before_shared_attempt,
                "provider_timeout_seconds": profile.provider_timeout_seconds,
                "primary_timeout_seconds": profile.primary_timeout_seconds,
                "allow_sticky_fallback": profile.allow_sticky_fallback,
            }
            if user_models:
                gen_kwargs["user_provider_models"] = user_models
            try:
                generated = active_generator.generate(
                    normalized_query,
                    evidence,
                    **gen_kwargs,
                )
            except TypeError:
                try:
                    generated = active_generator.generate(
                        normalized_query,
                        evidence,
                        user_api_keys=user_keys or None,
                    )
                except TypeError:
                    generated = active_generator.generate(normalized_query, evidence)

            validated = CitationValidator().validate(generated, evidence)
            if not validated.citations:
                # An answer that cites none of the evidence is not grounded;
                # report insufficient evidence instead of an unsupported reply.
                insufficient = True

            last_resp = getattr(active_generator, "last_response", None)
            if last_resp is not None:
                used_byok = bool(getattr(last_resp, "used_byok", False))
                usage_obj = getattr(last_resp, "usage", None)
                prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
                total_tokens = int(getattr(usage_obj, "total_tokens", 0) or (prompt_tokens + completion_tokens))
                if used_byok:
                    api_key_service.record_key_usage(
                        session,
                        user_id,
                        last_resp.provider,
                        tokens=total_tokens,
                    )
                usage_source = (
                    "byok"
                    if used_byok
                    else ("local" if last_resp.provider == "ollama" else "shared")
                )
                was_reserved = bool(record.shared_quota_reserved)
                if insufficient or usage_source in ("byok", "local"):
                    if was_reserved:
                        release_research_shared_quota(session, record.id, commit=False)
                elif usage_source == "shared":
                    settle_research_shared_quota(
                        session,
                        research_id=record.id,
                        user_id=user_id,
                        actual_provider=last_resp.provider,
                        settings=runtime_settings,
                        commit=False,
                    )

                cost_usd = estimate_cost_usd(
                    last_resp.provider,
                    prompt_tokens,
                    completion_tokens,
                )
                record_model_usage(
                    session,
                    user_id=user_id,
                    provider=last_resp.provider,
                    model_name=last_resp.model,
                    usage_source=usage_source,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    estimated_cost_usd=cost_usd,
                    increment_shared_quota=False,
                    commit=False,
                )
                if runtime_settings.telemetry_enabled:
                    record_telemetry_event(
                        session,
                        event_type="llm_generation",
                        operation="research_answer",
                        provider=last_resp.provider,
                        model=last_resp.model,
                        status="success",
                        latency_ms=getattr(last_resp, "latency_ms", None),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        user_id=user_id,
                        metadata={
                            "used_byok": used_byok,
                            "is_local": last_resp.provider == "ollama",
                            "depth": str(record.research_depth),
                            "research_id": str(record.id),
                        },
                        settings=runtime_settings,
                        commit=False,
                    )
        if (
            not insufficient
            and settings.chat_title_llm_enabled
            and research.is_auto_generated_title(record.title, record.question)
            and hasattr(active_generator, "generate_short_title")
        ):
            title_provider = last_resp.provider if last_resp is not None else pref_provider
            title_model = (
                str(model_override)
                if model_override and title_provider == pref_provider
                else None
            )
            title_local = (
                True
                if (last_resp is not None and last_resp.provider == "ollama")
                else (bool(local_fallback) if local_fallback is not None else None)
            )
            raw_title = active_generator.generate_short_title(
                normalized_query,
                user_api_keys=user_keys or None,
                user_provider_models=user_models or None,
                preferred_provider=title_provider,
                model_override=title_model,
                local_fallback_enabled=title_local,
                allow_shared_providers=bool(record.allow_shared_providers),
            )
            if raw_title:
                record.title = normalize_short_title(
                    raw_title, fallback_question=record.question
                )
                session.add(record)

        if (
            record.title == research.legacy_fallback_title(record.question)
            and len(record.title.split()) > MAX_CHAT_TITLE_WORDS
        ):
            record.title = research.build_fallback_title(record.question)
            session.add(record)

        if insufficient:
            release_research_shared_quota(session, record.id, commit=False)
            answer = INSUFFICIENT_EVIDENCE_ANSWER
            validated = CitationValidator().validate(answer, evidence)
        else:
            answer = validated.answer

        reports.persist_report(
            session,
            record.id,
            _report_payload(
                research_id=record.id,
                title=record.title,
                answer=answer,
                citations=validated.citations,
                evidence=evidence,
            ),
            commit=False,
        )
        research.advance_research_progress(
            session,
            record.id,
            project_status=ProjectStatus.REPORT_READY,
            commit=True,
        )
        logger.info(
            "Completed research execution",
            extra={
                "research_id": str(record.id),
                "mode": profile.mode,
                "depth": str(record.research_depth),
                "candidates": len(candidates),
                "evidence": len(evidence),
                "duration_ms": round((monotonic() - started_at) * 1000, 1),
            },
        )
        return ResearchQueryResponse(
            research_id=record.id,
            project_id=record.project_id,
            answer=answer,
            citations=validated.citations,
            hybrid_candidate_count=len(candidates),
            evidence_count=len(evidence),
            insufficient_evidence=insufficient,
        )
    except AppError as exc:
        session.rollback()
        release_research_shared_quota(session, record.id, commit=False)
        _remember_model_failure(session, record, exc, user_id, runtime_settings)
        research.mark_research_failed(session, record.id)
        raise
    except Exception as exc:
        session.rollback()
        release_research_shared_quota(session, record.id, commit=False)
        research.mark_research_failed(session, record.id)
        raise AppError(
            "The grounded research request could not be completed",
            status_code=500,
            code="research_pipeline_failed",
        ) from exc


def _compact_memory_text(value: str | None, limit: int) -> str:
    cleaned = " ".join((value or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(1, limit - 1)].rstrip()}…"


def _build_compact_report_memory(
    record: Research,
    report_title: str,
    report_summary: str,
    prior_followups: list[ReportFollowup],
) -> str:
    """Build a strictly bounded report memory (~<=1.4k chars) for low-token follow-ups."""
    lines = [
        f"Original question: {_compact_memory_text(record.question, 200)}",
        f"Report title: {_compact_memory_text(report_title, 140)}",
        f"Report summary: {_compact_memory_text(report_summary, 620)}",
    ]
    for index, turn in enumerate(prior_followups[-2:], start=1):
        lines.append(f"Earlier follow-up {index}: {_compact_memory_text(turn.question, 140)}")
        lines.append(f"Earlier answer {index}: {_compact_memory_text(turn.answer, 240)}")
    return "\n".join(lines)


def _source_to_evidence_item(
    source: Source,
    *,
    research_id: UUID,
    project_id: UUID | None,
) -> EvidenceItem | None:
    excerpt = (source.relevant_excerpt or "").strip()
    if not excerpt:
        return None
    raw_source_type = getattr(source.source_type, "value", source.source_type)
    try:
        evidence_source_type = DocumentSourceType(raw_source_type) if raw_source_type else None
    except ValueError:
        evidence_source_type = None
    return EvidenceItem(
        source_id=f"S{source.number}",
        node_id=None,
        document_id=source.document_id or uuid5(research_id, f"source-doc-{source.number}"),
        project_id=project_id,
        source_type=evidence_source_type,
        content_level=None,
        chunk_id=source.chunk_id or uuid5(research_id, f"source-chunk-{source.number}"),
        paper_title=source.title,
        authors=list(source.authors or []),
        doi=source.doi,
        url=source.url,
        publisher=source.publisher,
        year=source.year,
        page=source.page,
        page_end=None,
        section=source.section,
        section_path=None,
        text=excerpt,
        rerank_score=float(source.rerank_score or 0.5),
    )


def _build_followup_evidence(
    session: Session,
    *,
    record: Research,
    user_id: UUID,
    question: str,
    existing_sources: list[Source],
    settings: Settings,
    reranker: RerankerService | None,
) -> list[EvidenceItem]:
    """Retrieve focused chunks from this report's sources and preserve existing [S#] labels."""
    followup_settings = settings.model_copy(
        update={
            "vector_top_k": min(settings.vector_top_k, 10),
            "keyword_top_k": min(settings.keyword_top_k, 10),
            "hybrid_candidate_k": min(settings.hybrid_candidate_k, 10),
            "reranker_provider": (
                "lexical"
                if settings.adaptive_fast_path_enabled
                else settings.reranker_provider
            ),
            "final_context_k": min(settings.final_context_k, 4),
        }
    )
    doc_scope = scoped_document_ids(record)
    if doc_scope is None and record.project_id is None:
        source_doc_ids = list({s.document_id for s in existing_sources if s.document_id is not None})
        doc_scope = source_doc_ids or None

    retrieval_query = (
        f"{question} {record.question[:120]}"
        if len(question.split()) <= 8
        else question
    )
    candidates = retrieval.retrieve(
        session,
        user_id,
        retrieval_query,
        followup_settings,
        project_id=record.project_id,
        document_ids=doc_scope,
    )
    ranked = (
        (reranker or reranker_service_for(followup_settings)).rerank(retrieval_query, candidates)
        if candidates
        else []
    )
    fresh_evidence = build_evidence(ranked, followup_settings, "quick")

    source_by_chunk = {s.chunk_id: s for s in existing_sources if s.chunk_id is not None}
    next_number = max((s.number for s in existing_sources), default=0) + 1
    selected: list[EvidenceItem] = []
    seen_ids: set[str] = set()
    seen_chunks: set[UUID] = set()

    for item in fresh_evidence:
        if item.chunk_id in source_by_chunk:
            existing_src = source_by_chunk[item.chunk_id]
            sid = f"S{existing_src.number}"
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            seen_chunks.add(item.chunk_id)
            selected.append(item.model_copy(update={"source_id": sid}))
            continue
        sid = f"S{next_number}"
        next_number += 1
        seen_ids.add(sid)
        seen_chunks.add(item.chunk_id)
        selected.append(item.model_copy(update={"source_id": sid}))

    # Include compact excerpts from the report's existing sources as fallback context so
    # conversational follow-ups ("summarize point 2") stay grounded even without keyword overlap.
    for src in existing_sources:
        if len(selected) >= 5:
            break
        sid = f"S{src.number}"
        if sid in seen_ids or (src.chunk_id is not None and src.chunk_id in seen_chunks):
            continue
        converted = _source_to_evidence_item(
            src,
            research_id=record.id,
            project_id=record.project_id,
        )
        if converted is not None:
            seen_ids.add(sid)
            selected.append(converted)

    return selected


def ask_report_followup(
    session: Session,
    *,
    user_id: UUID,
    research_id: UUID,
    payload: ReportFollowupRequest,
    settings: Settings | None = None,
    reranker: RerankerService | None = None,
    generator: GenerationService | None = None,
) -> ReportFollowupCreateResponse:
    """Answer a lightweight follow-up on a composed report using tiny memory and 0.25x credit."""
    from app.services.auth import api_keys as api_key_service

    runtime_settings = settings or get_settings()
    record, _ = require_research_access(
        session, research_id, user_id, min_role=CollaboratorRole.EDITOR
    )
    composed_report = reports._load_report(session, research_id)
    if composed_report is None:
        raise AppError(
            "Research report is not ready",
            status_code=404,
            code="research_report_not_ready",
        )

    normalized_question = payload.question.strip()
    if not normalized_question:
        raise AppError(
            "A follow-up question is required",
            status_code=422,
            code="followup_question_required",
        )

    existing_sources = reports.list_report_sources(session, research_id)
    prior_followups = list(composed_report.followups)
    evidence = _build_followup_evidence(
        session,
        record=record,
        user_id=user_id,
        question=normalized_question,
        existing_sources=existing_sources,
        settings=runtime_settings,
        reranker=reranker,
    )

    pref_provider = (
        payload.preferred_provider.strip().lower()
        if payload.preferred_provider
        else record.preferred_provider
    )
    model_override = (
        payload.model_override.strip()
        if payload.model_override
        else record.model_override
    )
    local_fallback = _first_set(
        payload.local_fallback_enabled,
        api_key_service.get_local_fallback_pref(session, user_id),
        record.local_fallback_enabled,
    )
    user_keys = api_key_service.get_decrypted_user_api_keys(session, user_id, runtime_settings)
    user_models = api_key_service.get_user_provider_models(session, user_id)

    followup_id = uuid4()
    allow_shared, quota_reserved, _, _ = acquire_run_quota_policy(
        session,
        user_id=user_id,
        preferred_provider=pref_provider,
        user_byok_providers=set(user_keys.keys()),
        local_enabled=bool(local_fallback),
        research_id=followup_id,
        units=CREDIT_UNITS_FOLLOWUP,
        settings=runtime_settings,
    )

    compact_memory = _build_compact_report_memory(
        record,
        composed_report.title,
        composed_report.summary,
        prior_followups,
    )
    compact_runtime_settings = runtime_settings.model_copy(
        update={
            "generation_max_new_tokens": min(runtime_settings.generation_max_new_tokens, 384),
        }
    )

    insufficient = not evidence_is_sufficient(
        evidence,
        minimum_count=runtime_settings.minimum_evidence_count,
        minimum_relevance=runtime_settings.reranker_min_score,
    )

    actual_provider: str | None = None
    actual_model: str | None = None
    credit_cost = 0.0
    try:
        validated_citation_nums: list[int] = []
        if not insufficient:
            active_generator = generator or generation_service_for(compact_runtime_settings)

            def _before_shared_attempt(attempted_provider: str) -> bool:
                return ensure_research_shared_quota(
                    session,
                    research_id=followup_id,
                    user_id=user_id,
                    provider=attempted_provider,
                    units=CREDIT_UNITS_FOLLOWUP,
                    settings=runtime_settings,
                    commit=True,
                )

            gen_kwargs: dict[str, object] = {
                "report_memory": compact_memory,
                "user_api_keys": user_keys or None,
                "preferred_provider": pref_provider or None,
                "model_override": model_override or None,
                "local_fallback_enabled": (
                    bool(local_fallback) if local_fallback is not None else None
                ),
                "allow_shared_providers": bool(allow_shared),
                "before_shared_attempt": _before_shared_attempt,
                "provider_timeout_seconds": min(runtime_settings.llm_quick_timeout_seconds, 20.0),
                "primary_timeout_seconds": runtime_settings.gemini_primary_timeout_seconds,
                "allow_sticky_fallback": True,
            }
            if user_models:
                gen_kwargs["user_provider_models"] = user_models

            try:
                generated = active_generator.generate(
                    normalized_question,
                    evidence,
                    **gen_kwargs,
                )
            except TypeError:
                try:
                    fallback_kwargs = {k: v for k, v in gen_kwargs.items() if k != "report_memory"}
                    generated = active_generator.generate(
                        normalized_question,
                        evidence,
                        **fallback_kwargs,
                    )
                except TypeError:
                    generated = active_generator.generate(normalized_question, evidence)

            validated = CitationValidator().validate(generated, evidence)
            if not validated.citations:
                insufficient = True
            else:
                answer = validated.answer.strip()
                validated_citation_nums = list(
                    dict.fromkeys(int(c.citation_id[1:]) for c in validated.citations)
                )

            last_resp = getattr(active_generator, "last_response", None)
            if last_resp is not None:
                actual_provider = last_resp.provider
                actual_model = last_resp.model
                used_byok = bool(getattr(last_resp, "used_byok", False))
                usage_obj = getattr(last_resp, "usage", None)
                prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
                total_tokens = int(
                    getattr(usage_obj, "total_tokens", 0) or (prompt_tokens + completion_tokens)
                )
                if used_byok:
                    api_key_service.record_key_usage(
                        session,
                        user_id,
                        last_resp.provider,
                        tokens=total_tokens,
                    )
                usage_source = (
                    "byok"
                    if used_byok
                    else ("local" if last_resp.provider == "ollama" else "shared")
                )
                if insufficient or usage_source in ("byok", "local"):
                    if quota_reserved:
                        release_research_shared_quota(
                            session,
                            followup_id,
                            user_id=user_id,
                            commit=False,
                        )
                    credit_cost = 0.0
                else:
                    settle_research_shared_quota(
                        session,
                        research_id=followup_id,
                        user_id=user_id,
                        actual_provider=last_resp.provider,
                        units=CREDIT_UNITS_FOLLOWUP,
                        settings=runtime_settings,
                        commit=False,
                    )
                    credit_cost = 0.25

                cost_usd = estimate_cost_usd(
                    last_resp.provider,
                    prompt_tokens,
                    completion_tokens,
                )
                record_model_usage(
                    session,
                    user_id=user_id,
                    provider=last_resp.provider,
                    model_name=last_resp.model,
                    usage_source=usage_source,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    estimated_cost_usd=cost_usd,
                    increment_shared_quota=False,
                    commit=False,
                )
                if runtime_settings.telemetry_enabled:
                    record_telemetry_event(
                        session,
                        event_type="llm_generation",
                        operation="report_followup",
                        provider=last_resp.provider,
                        model=last_resp.model,
                        status="success",
                        latency_ms=getattr(last_resp, "latency_ms", None),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        user_id=user_id,
                        metadata={
                            "used_byok": used_byok,
                            "is_local": last_resp.provider == "ollama",
                            "research_id": str(research_id),
                            "followup_id": str(followup_id),
                        },
                        settings=runtime_settings,
                        commit=False,
                    )

            if not insufficient:
                existing_numbers = {s.number for s in existing_sources}
                evidence_by_id = {item.source_id: item for item in evidence}
                for cit in validated.citations:
                    source_num = int(cit.citation_id[1:])
                    if source_num in existing_numbers:
                        continue
                    item = evidence_by_id[cit.citation_id]
                    raw_authors = [
                        name.strip()[:200]
                        for name in (cit.authors or [])[:50]
                        if isinstance(name, str) and name.strip()
                    ]
                    raw_year = getattr(item, "year", None)
                    safe_year = raw_year if isinstance(raw_year, int) and 1000 <= raw_year <= 9999 else None
                    raw_url = getattr(cit, "url", None) or (
                        f"https://doi.org/{cit.doi}" if cit.doi else None
                    )
                    new_src = Source(
                        id=uuid5(research_id, cit.citation_id),
                        research_id=research_id,
                        number=source_num,
                        title=_truncate_str(cit.paper_title, 500),
                        publisher=_truncate_str(getattr(item, "publisher", None), 200),
                        authors=raw_authors,
                        year=safe_year,
                        url=_truncate_str(raw_url, 2048),
                        source_type=_report_source_type(item),
                        relevant_excerpt=cit.excerpt,
                        doi=_truncate_str(cit.doi, 255),
                        document_id=cit.document_id,
                        chunk_id=cit.chunk_id,
                        page=cit.page,
                        section=_truncate_str(cit.section, 500),
                        rerank_score=item.rerank_score,
                    )
                    session.add(new_src)
                    existing_numbers.add(source_num)

        if insufficient:
            if quota_reserved:
                release_research_shared_quota(
                    session,
                    followup_id,
                    user_id=user_id,
                    commit=False,
                )
            credit_cost = 0.0
            answer = INSUFFICIENT_EVIDENCE_ANSWER
            validated_citation_nums = []

        # Lock the parent report row (Postgres) and compute the next position atomically
        # so simultaneous follow-ups from collaborators never collide on position.
        session.execute(
            select(ResearchReport.id)
            .where(ResearchReport.id == composed_report.id)
            .with_for_update()
        ).first()
        current_max_position = session.scalar(
            select(func.max(ReportFollowup.position)).where(
                ReportFollowup.report_id == composed_report.id
            )
        )
        next_position = (-1 if current_max_position is None else int(current_max_position)) + 1
        followup_row = ReportFollowup(
            id=followup_id,
            report_id=composed_report.id,
            user_id=user_id,
            question=normalized_question,
            answer=answer,
            citation_numbers=validated_citation_nums,
            position=next_position,
            provider=actual_provider,
            model=actual_model,
            insufficient_evidence=insufficient,
        )
        session.add(followup_row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # SQLite concurrent write fallback: recompute next position and commit cleanly.
            retry_max = session.scalar(
                select(func.max(ReportFollowup.position)).where(
                    ReportFollowup.report_id == composed_report.id
                )
            )
            followup_row = ReportFollowup(
                id=followup_id,
                report_id=composed_report.id,
                user_id=user_id,
                question=normalized_question,
                answer=answer,
                citation_numbers=validated_citation_nums,
                position=(-1 if retry_max is None else int(retry_max)) + 1,
                provider=actual_provider,
                model=actual_model,
                insufficient_evidence=insufficient,
            )
            session.add(followup_row)
            session.commit()
        session.refresh(followup_row)
        updated_sources = reports.list_report_sources(session, research_id)
        serialized_followup = reports.serialize_followup(followup_row, session=session)
        serialized_sources = [reports.serialize_source(s) for s in updated_sources]
        rooms = [research_room(research_id)]
        if record.project_id is not None:
            rooms.append(project_room(record.project_id))
        publish_realtime_event(
            rooms,
            "followup.created",
            {
                "researchId": str(research_id),
                "projectId": str(record.project_id) if record.project_id else None,
                "followup": serialized_followup.model_dump(by_alias=True, mode="json"),
                "sources": [
                    item.model_dump(by_alias=True, mode="json") for item in serialized_sources
                ],
            },
            actor=actor_for_user(session, user_id),
        )
        return ReportFollowupCreateResponse(
            followup=serialized_followup,
            sources=serialized_sources,
            credit_cost=credit_cost,
        )
    except AppError:
        session.rollback()
        if quota_reserved:
            release_research_shared_quota(session, followup_id, user_id=user_id, commit=True)
        raise
    except Exception as exc:
        session.rollback()
        if quota_reserved:
            release_research_shared_quota(session, followup_id, user_id=user_id, commit=True)
        raise AppError(
            "The follow-up answer could not be generated right now",
            status_code=500,
            code="report_followup_failed",
        ) from exc
