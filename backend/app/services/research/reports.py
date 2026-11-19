from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.domain.collaboration import CollaboratorRole
from app.models.report import Citation, ReportFollowup, ReportSection, ResearchReport, Source
from app.models.user import User
from app.schemas.reports import (
    CitationResponse,
    ComposedReportResponse,
    ReportFollowupResponse,
    ReportSectionResponse,
    ResearchReportCreate,
    ResearchReportResponse,
    SourceResponse,
)
from app.services.collaboration.access import require_research_access
from app.services.collaboration.service import attach_research_collab_metadata
from app.services.research.runs import get_research


def _invalid_evidence(message: str) -> AppError:
    return AppError(message, status_code=422, code="invalid_report_evidence")


def _validate_graph(payload: ResearchReportCreate) -> None:
    source_ids = [source.id for source in payload.sources]
    source_numbers = [source.number for source in payload.sources]
    section_ids = [section.id for section in payload.sections]
    section_positions = [section.position for section in payload.sections]

    if len(source_ids) != len(set(source_ids)):
        raise _invalid_evidence("Source IDs must be unique within a report")
    if len(source_numbers) != len(set(source_numbers)):
        raise _invalid_evidence("Source numbers must be unique within a report")
    if len(section_ids) != len(set(section_ids)):
        raise _invalid_evidence("Section IDs must be unique within a report")
    if len(section_positions) != len(set(section_positions)):
        raise _invalid_evidence("Section positions must be unique within a report")

    valid_source_ids = set(source_ids)
    for section in payload.sections:
        citation_positions = [citation.position for citation in section.citations]
        citation_source_ids = [citation.source_id for citation in section.citations]
        if len(citation_positions) != len(set(citation_positions)):
            raise _invalid_evidence(
                f"Citation positions must be unique in section {section.id}"
            )
        if len(citation_source_ids) != len(set(citation_source_ids)):
            raise _invalid_evidence(
                f"Each source may be linked once in section {section.id}"
            )
        if unknown_ids := set(citation_source_ids) - valid_source_ids:
            unknown = ", ".join(sorted(str(source_id) for source_id in unknown_ids))
            raise _invalid_evidence(f"Citations reference unknown sources: {unknown}")


def persist_report(
    session: Session,
    research_id: UUID,
    payload: ResearchReportCreate,
    *,
    commit: bool = True,
) -> ResearchReport:
    """Atomically persist a future pipeline's report and evidence graph.

    No report content or source data is generated here. The caller must provide
    the complete grounded payload, including stable source numbers and links.
    """
    research = get_research(session, research_id)
    if (
        session.scalar(
            select(ResearchReport.id).where(ResearchReport.research_id == research_id)
        )
        is not None
    ):
        raise AppError(
            "A current report already exists for this research",
            status_code=409,
            code="research_report_exists",
        )

    _validate_graph(payload)
    report = ResearchReport(
        id=payload.id,
        research=research,
        title=payload.title,
        summary=payload.summary,
        dossier_ref=payload.dossier_ref,
        reading_time_minutes=payload.reading_time_minutes,
        version=payload.version,
    )
    source_by_id: dict[UUID, Source] = {}
    for source_payload in payload.sources:
        source = Source(
            id=source_payload.id,
            research=research,
            number=source_payload.number,
            title=source_payload.title,
            publisher=source_payload.publisher,
            authors=source_payload.authors,
            year=source_payload.year,
            url=source_payload.url,
            source_type=source_payload.source_type,
            relevant_excerpt=source_payload.relevant_excerpt,
            doi=source_payload.doi,
            bibtex=source_payload.bibtex,
            document_id=source_payload.document_id,
            chunk_id=source_payload.chunk_id,
            page=source_payload.page,
            section=source_payload.section,
            rerank_score=source_payload.rerank_score,
        )
        source_by_id[source.id] = source
        session.add(source)

    for section_payload in payload.sections:
        section = ReportSection(
            id=section_payload.id,
            report=report,
            heading=section_payload.heading,
            content=section_payload.content,
            quote=section_payload.quote,
            position=section_payload.position,
        )
        for citation_payload in section_payload.citations:
            section.citations.append(
                Citation(
                    source=source_by_id[citation_payload.source_id],
                    position=citation_payload.position,
                )
            )
        report.sections.append(section)

    session.add(report)
    try:
        if commit:
            session.commit()
        else:
            session.flush()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AppError(
            "The report and evidence could not be saved",
            status_code=500,
            code="report_persistence_error",
        ) from exc
    if commit:
        session.refresh(report)
    return report


def _load_report(session: Session, research_id: UUID) -> ResearchReport | None:
    return session.scalar(
        select(ResearchReport)
        .where(ResearchReport.research_id == research_id)
        .options(
            selectinload(ResearchReport.research),
            selectinload(ResearchReport.sections)
            .selectinload(ReportSection.citations)
            .selectinload(Citation.source),
            selectinload(ResearchReport.followups),
        )
    )


def serialize_source(source: Source) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        number=source.number,
        title=source.title,
        publisher=source.publisher,
        authors=source.authors,
        year=source.year,
        url=source.url,
        source_type=source.source_type,
        relevant_excerpt=source.relevant_excerpt,
        citation_count=len(source.citations),
        doi=source.doi,
        bibtex=source.bibtex,
        document_id=source.document_id,
        chunk_id=source.chunk_id,
        page=source.page,
        section=source.section,
        rerank_score=source.rerank_score,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def serialize_followup(
    followup: ReportFollowup,
    *,
    author_names: dict[UUID, str] | None = None,
    session: Session | None = None,
) -> ReportFollowupResponse:
    author_name: str | None = None
    if followup.user_id is not None:
        if author_names is not None and followup.user_id in author_names:
            author_name = author_names[followup.user_id]
        elif session is not None:
            author_name = session.scalar(
                select(User.name).where(User.id == followup.user_id)
            )
    return ReportFollowupResponse(
        id=followup.id,
        report_id=followup.report_id,
        author_id=followup.user_id,
        author_name=author_name,
        question=followup.question,
        answer=followup.answer,
        citation_ids=list(followup.citation_numbers or []),
        position=followup.position,
        provider=followup.provider,
        model=followup.model,
        insufficient_evidence=followup.insufficient_evidence,
        created_at=followup.created_at,
        updated_at=followup.updated_at,
    )


def list_report_sources(session: Session, research_id: UUID) -> list[Source]:
    return list(
        session.scalars(
            select(Source)
            .where(Source.research_id == research_id)
            .options(selectinload(Source.citations))
            .order_by(Source.number)
        ).all()
    )


def get_composed_report(
    session: Session,
    research_id: UUID,
    user_id: UUID | None = None,
) -> ComposedReportResponse:
    research, my_role = require_research_access(
        session, research_id, user_id, min_role=CollaboratorRole.VIEWER
    )
    attach_research_collab_metadata(session, [research], user_id)
    report = _load_report(session, research_id)
    if report is None:
        raise AppError(
            "Research report is not ready",
            status_code=404,
            code="research_report_not_ready",
        )

    sources = list_report_sources(session, research_id)
    section_responses: list[ReportSectionResponse] = []
    for section in report.sections:
        citations = [
            CitationResponse(
                id=citation.id,
                source_id=citation.source_id,
                number=citation.source.number,
                position=citation.position,
            )
            for citation in section.citations
        ]
        section_responses.append(
            ReportSectionResponse(
                id=section.id,
                heading=section.heading,
                content=section.content,
                quote=section.quote,
                position=section.position,
                citation_ids=[citation.number for citation in citations],
                citations=citations,
                created_at=section.created_at,
                updated_at=section.updated_at,
            )
        )

    source_responses = [serialize_source(source) for source in sources]
    followup_author_ids = {item.user_id for item in report.followups if item.user_id is not None}
    author_names: dict[UUID, str] = {}
    if followup_author_ids:
        author_names = dict(
            session.execute(
                select(User.id, User.name).where(User.id.in_(followup_author_ids))
            ).all()
        )
    followup_responses = [
        serialize_followup(item, author_names=author_names) for item in report.followups
    ]
    return ComposedReportResponse(
        report=ResearchReportResponse(
            id=report.id,
            research_id=report.research_id,
            title=report.title,
            summary=report.summary,
            dossier_ref=report.dossier_ref,
            reading_time_minutes=report.reading_time_minutes,
            source_count=len(sources),
            status=research.status,
            version=report.version,
            my_role=my_role,
            is_shared=bool(getattr(research, "is_shared", False)),
            sections=section_responses,
            created_at=report.created_at,
            updated_at=report.updated_at,
        ),
        sources=source_responses,
        followups=followup_responses,
    )
