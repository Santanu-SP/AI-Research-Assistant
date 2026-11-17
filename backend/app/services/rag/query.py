"""Orchestration for the authenticated grounded local RAG request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
import re
from time import monotonic
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.domain.reports import SourceType
from app.domain.research import ResearchDepth, ResearchStatus
from app.domain.states import ProjectStatus
from app.schemas.rag import ResearchQueryRequest, ResearchQueryResponse, ResearchRetryRequest
from app.schemas.reports import ResearchReportCreate
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
from app.models.research import Research
from app.services.jobs import queue as job_queue
from app.services.observability.telemetry import estimate_cost_usd, record_telemetry_event
from app.services.observability.usage import (
    acquire_run_quota_policy,
    record_model_usage,
    release_research_shared_quota,
    reserve_shared_quota_slot,
)
from app.services.research import reports
from app.services.research import runs as research

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


def prepare_discovered_documents_if_requested(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    storage,
    settings: Settings,
) -> ResearchQueryRequest:
    """When ``auto_discover`` is opted in with no picked documents, discover & ingest curated sources."""
    if not payload.auto_discover or (payload.document_ids and len(payload.document_ids) > 0):
        return payload

    from app.services.discovery import service as discovery_service

    search_result = discovery_service.search_and_annotate(
        session,
        user_id=user_id,
        query=payload.query,
        scope=payload.discovery_scope,
        limit=settings.discovery_max_results,
        project_id=payload.project_id,
        settings=settings,
    )
    selected = search_result.items[: settings.discovery_auto_import_limit]
    if not selected:
        raise AppError(
            "No trustworthy external sources were found for this question.",
            status_code=422,
            code="no_discoverable_sources",
        )

    imported = discovery_service.import_discovered_sources(
        session,
        selected,
        storage=storage,
        settings=settings,
        user_id=user_id,
        project_id=payload.project_id,
        fetch_full_text=True,
    )
    doc_ids = [doc.id for doc in imported.documents]
    if not doc_ids:
        raise AppError(
            "Found external references could not be extracted into readable evidence.",
            status_code=422,
            code="no_discoverable_sources",
        )
    return payload.model_copy(update={"document_ids": doc_ids})


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
    """Create a research run and leave the work to the background worker."""
    duplicate = find_recent_duplicate(session, user_id, payload)
    if duplicate is not None:
        return duplicate
    record = _create_started_record(session, user_id, payload, settings)
    job_queue.enqueue(session, job_queue.RUN_RESEARCH, record.id)
    return research.get_research(session, record.id, user_id)


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
        settings=settings,
    )
    record.preferred_provider = pref_provider or None
    record.model_override = override or None
    record.local_fallback_enabled = local_fallback
    record.allow_shared_providers = allow_shared
    record.shared_quota_reserved = quota_reserved
    record.shared_quota_date = quota_date
    return bool(quota_reserved), quota_date


def _release_on_error(session: Session, user_id: UUID, reserved: bool, quota_date) -> None:
    if reserved and quota_date is not None:
        session.rollback()
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
        session.add(record)
        research.start_research(session, record.id)
    except Exception:
        _release_on_error(session, user_id, reserved, quota_date)
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
    record = research.get_research(session, research_id, user_id)
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
        if record.title == research.build_fallback_title(record.question):
            record.title = research.build_fallback_title(new_question)
        record.question = new_question
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
        _release_on_error(session, user_id, reserved, quota_date)
        raise
    return research.get_research(session, record.id, user_id)


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
        candidates = retrieval.retrieve(
            session,
            user_id,
            normalized_query,
            runtime_settings,
            project_id=record.project_id,
            document_ids=scoped_document_ids(record),
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

            def _before_shared_attempt(_provider: str) -> bool:
                fresh = session.get(Research, record.id)
                if fresh is not None and fresh.shared_quota_reserved:
                    return True
                reserved_ok, reserved_day, _ = reserve_shared_quota_slot(
                    session,
                    user_id=user_id,
                    settings=runtime_settings,
                    commit=True,
                )
                if not reserved_ok:
                    return False
                if fresh is not None:
                    fresh.shared_quota_reserved = True
                    fresh.shared_quota_date = reserved_day
                    session.add(fresh)
                    session.commit()
                return True

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
                if usage_source in ("byok", "local") and was_reserved:
                    release_research_shared_quota(session, record.id, commit=False)
                elif usage_source == "shared" and was_reserved:
                    record.shared_quota_reserved = False
                    record.shared_quota_date = None
                    session.add(record)

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
                    increment_shared_quota=(usage_source == "shared" and not was_reserved),
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
            validated = CitationValidator().validate(generated, evidence)
            if not validated.citations:
                # An answer that cites none of the evidence is not grounded;
                # report insufficient evidence instead of an unsupported reply.
                insufficient = True
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
