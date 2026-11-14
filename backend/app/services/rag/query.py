"""Orchestration for the authenticated grounded local RAG request."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import logging
import re
from threading import RLock
from time import monotonic
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.reports import SourceType
from app.domain.research import ResearchDepth
from app.domain.states import ProjectStatus
from app.schemas.rag import ResearchQueryRequest, ResearchQueryResponse
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
from app.services.observability.telemetry import record_telemetry_event
from app.services.observability.usage import enforce_user_daily_model_quota
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

    return ResearchExecutionProfile(
        mode="deep",
        settings=settings,
        provider_timeout_seconds=provider_timeout,
        primary_timeout_seconds=primary_timeout,
        allow_sticky_fallback=allow_sticky,
    )


def _plain_answer(answer: str) -> str:
    without_references = SOURCE_REFERENCE.sub("", answer)
    without_reference_spacing = re.sub(
        r"[ \t]+([,.;:!?])", r"\1", without_references
    )
    return re.sub(r" {2,}", " ", without_reference_spacing).strip()


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
        source_payloads.append(
            {
                "id": source_uuid,
                "number": source_number,
                "title": citation.paper_title,
                "publisher": None,
                "authors": citation.authors or [],
                "year": None,
                "sourceType": SourceType.TECHNICAL_REPORT,
                "relevantExcerpt": citation.excerpt,
                "doi": citation.doi,
                "documentId": citation.document_id,
                "chunkId": citation.chunk_id,
                "page": citation.page,
                "section": citation.section,
                "rerankScore": item.rerank_score,
            }
        )
        citation_payloads.append({"sourceId": source_uuid, "position": position})

    display_answer = _plain_answer(answer)
    reading_minutes = max(1, len(display_answer.split()) // 200 + 1)
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
    record = _create_started_record(session, user_id, payload, settings)
    return execute_research(
        session,
        record.id,
        user_id,
        settings,
        reranker=reranker,
        generator=generator,
        commit_intermediate=False,
    )


def queue_query(
    session: Session,
    user_id: UUID,
    payload: ResearchQueryRequest,
    settings: Settings | None = None,
) -> Research:
    """Create a research run and leave the work to the background worker."""
    record = _create_started_record(session, user_id, payload, settings)
    job_queue.enqueue(session, job_queue.RUN_RESEARCH, record.id)
    return research.get_research(session, record.id, user_id)


_RUNTIME_OPTIONS_LOCK = RLock()
_RUNTIME_OPTIONS_MAXSIZE = 1024
_RESEARCH_RUNTIME_OPTIONS: OrderedDict[UUID, dict[str, object]] = OrderedDict()


def _store_runtime_options(
    research_id: UUID,
    *,
    preferred_provider: str | None,
    model_override: str | None,
    local_fallback_enabled: bool | None,
) -> None:
    if preferred_provider is None and model_override is None and local_fallback_enabled is None:
        return
    with _RUNTIME_OPTIONS_LOCK:
        _RESEARCH_RUNTIME_OPTIONS[research_id] = {
            "preferred_provider": preferred_provider,
            "model_override": model_override,
            "local_fallback_enabled": local_fallback_enabled,
        }
        _RESEARCH_RUNTIME_OPTIONS.move_to_end(research_id)
        while len(_RESEARCH_RUNTIME_OPTIONS) > _RUNTIME_OPTIONS_MAXSIZE:
            _RESEARCH_RUNTIME_OPTIONS.popitem(last=False)


def _pop_runtime_options(research_id: UUID) -> dict[str, object]:
    with _RUNTIME_OPTIONS_LOCK:
        return _RESEARCH_RUNTIME_OPTIONS.pop(research_id, {})


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
    if settings is not None:
        enforce_user_daily_model_quota(
            session,
            user_id,
            settings,
            preferred_provider=payload.preferred_provider,
        )
    record = research.create_research(
        session,
        ResearchCreate(
            question=normalized_query,
            project_id=payload.project_id,
            research_depth=payload.research_depth,
        ),
        user_id,
    )
    research.start_research(session, record.id)
    from app.services.auth import api_keys as api_key_service

    pref_provider = payload.preferred_provider.strip().lower() if payload.preferred_provider else None
    model_override = payload.model_override.strip() if payload.model_override else None
    local_fallback = (
        payload.local_fallback_enabled
        if payload.local_fallback_enabled is not None
        else api_key_service.get_local_fallback_pref(user_id)
    )
    _store_runtime_options(
        record.id,
        preferred_provider=pref_provider or None,
        model_override=model_override or None,
        local_fallback_enabled=local_fallback,
    )
    return record


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
        )
        if candidates:
            ranked = (reranker or reranker_service_for(runtime_settings)).rerank(
                normalized_query, candidates
            )
        else:
            ranked = []
        evidence = EvidenceBuilder().build(
            ranked, limit=runtime_settings.final_context_k
        )
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

            runtime_options = _pop_runtime_options(record.id)
            pref_provider = runtime_options.get("preferred_provider")
            model_override = runtime_options.get("model_override")
            local_fallback = runtime_options.get("local_fallback_enabled")
            if local_fallback is None:
                local_fallback = api_key_service.get_local_fallback_pref(user_id)

            user_keys = api_key_service.get_decrypted_user_api_keys(
                session, user_id, runtime_settings
            )
            user_models = api_key_service.get_user_provider_models(user_id)
            gen_kwargs: dict[str, object] = {
                "user_api_keys": user_keys or None,
                "preferred_provider": (str(pref_provider) if pref_provider else None),
                "model_override": (str(model_override) if model_override else None),
                "local_fallback_enabled": (
                    bool(local_fallback) if local_fallback is not None else None
                ),
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
    except AppError:
        session.rollback()
        research.mark_research_failed(session, record.id)
        raise
    except Exception as exc:
        session.rollback()
        research.mark_research_failed(session, record.id)
        raise AppError(
            "The grounded research request could not be completed",
            status_code=500,
            code="research_pipeline_failed",
        ) from exc
