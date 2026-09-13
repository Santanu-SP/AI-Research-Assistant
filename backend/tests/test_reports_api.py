from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.report import Citation, ReportSection, ResearchReport, Source
from app.models.research import Research
from app.schemas.reports import ResearchReportCreate
from app.services import reports as report_service


def create_research(client: TestClient, *, title: str = "Evidence review") -> UUID:
    response = client.post(
        "/api/v1/research",
        json={"question": "What does the available evidence show?", "title": title},
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def report_payload() -> ResearchReportCreate:
    first_source_id = uuid4()
    second_source_id = uuid4()
    return ResearchReportCreate(
        title="A grounded synthesis",
        summary="The available evidence supports a qualified conclusion.",
        dossier_ref="SYNTHESIS MEMO · REF #TEST-001",
        reading_time_minutes=6,
        version=1,
        sources=[
            {
                "id": first_source_id,
                "number": 1,
                "title": "Controlled empirical study",
                "publisher": "ACM",
                "authors": ["A. Researcher", "B. Reviewer"],
                "year": 2025,
                "url": "https://example.test/study",
                "sourceType": "peer-reviewed",
                "relevantExcerpt": "The controlled group improved measurably.",
                "doi": "10.1000/example",
                "bibtex": "@article{example2025}",
            },
            {
                "id": second_source_id,
                "number": 2,
                "title": "Institutional evidence review",
                "publisher": "Research Institute",
                "authors": ["C. Analyst"],
                "year": 2024,
                "sourceType": "institutional",
            },
        ],
        # Deliberately supplied out of order to prove persisted ordering is stable.
        sections=[
            {
                "heading": "Second section",
                "content": "The institutional review provides context.",
                "position": 1,
                "citations": [{"sourceId": second_source_id, "position": 0}],
            },
            {
                "heading": "First section",
                "content": "The controlled study supplies primary evidence.",
                "quote": "A grounded, attributable excerpt.",
                "position": 0,
                "citations": [
                    {"sourceId": second_source_id, "position": 1},
                    {"sourceId": first_source_id, "position": 0},
                ],
            },
        ],
    )


def test_internal_service_persists_complete_report_graph(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)

    report = report_service.persist_report(db_session, research_id, report_payload())

    assert report.research_id == research_id
    assert db_session.scalar(select(func.count()).select_from(ResearchReport)) == 1
    assert db_session.scalar(select(func.count()).select_from(ReportSection)) == 2
    assert db_session.scalar(select(func.count()).select_from(Source)) == 2
    assert db_session.scalar(select(func.count()).select_from(Citation)) == 3


def test_composed_response_is_ordered_and_frontend_ready(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    report_service.persist_report(db_session, research_id, report_payload())

    response = client.get(f"/api/v1/research/{research_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["researchId"] == str(research_id)
    assert body["report"]["dossierRef"] == "SYNTHESIS MEMO · REF #TEST-001"
    assert body["report"]["readingTimeMinutes"] == 6
    assert body["report"]["sourceCount"] == 2
    assert body["report"]["status"] == "draft"
    assert body["report"]["version"] == 1
    assert [section["heading"] for section in body["report"]["sections"]] == [
        "First section",
        "Second section",
    ]
    assert body["report"]["sections"][0]["citationIds"] == [1, 2]
    assert [
        citation["number"] for citation in body["report"]["sections"][0]["citations"]
    ] == [1, 2]
    assert [source["number"] for source in body["sources"]] == [1, 2]
    assert body["sources"][0]["sourceType"] == "peer-reviewed"
    assert body["sources"][0]["relevantExcerpt"].startswith("The controlled")
    assert body["sources"][0]["citationCount"] == 1
    assert body["sources"][1]["citationCount"] == 2
    assert body["report"]["createdAt"].endswith("Z")


def test_citations_reference_persisted_sources(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    report_service.persist_report(db_session, research_id, report_payload())

    citations = list(db_session.scalars(select(Citation)).all())

    assert all(citation.source is not None for citation in citations)
    assert {citation.source.number for citation in citations} == {1, 2}
    assert all(citation.source.research_id == research_id for citation in citations)


def test_report_missing_returns_truthful_not_ready_error(client: TestClient) -> None:
    research_id = create_research(client)

    response = client.get(f"/api/v1/research/{research_id}/report")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "research_report_not_ready",
            "message": "Research report is not ready",
        }
    }


def test_missing_research_returns_existing_not_found_error(client: TestClient) -> None:
    response = client.get(f"/api/v1/research/{uuid4()}/report")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_not_found"


def test_archived_research_hides_its_report(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    report_service.persist_report(db_session, research_id, report_payload())
    assert client.delete(f"/api/v1/research/{research_id}").status_code == 204

    response = client.get(f"/api/v1/research/{research_id}/report")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_not_found"


def test_unknown_source_reference_is_rejected_without_partial_writes(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    payload = report_payload()
    payload.sections[0].citations[0].source_id = uuid4()

    with pytest.raises(AppError) as error:
        report_service.persist_report(db_session, research_id, payload)

    assert error.value.status_code == 422
    assert error.value.code == "invalid_report_evidence"
    assert db_session.scalar(select(func.count()).select_from(ResearchReport)) == 0
    assert db_session.scalar(select(func.count()).select_from(Source)) == 0


def test_duplicate_positions_and_numbers_are_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    duplicate_sections = report_payload()
    duplicate_sections.sections[1].position = duplicate_sections.sections[0].position

    with pytest.raises(AppError, match="Section positions"):
        report_service.persist_report(db_session, research_id, duplicate_sections)

    duplicate_sources = report_payload()
    duplicate_sources.sources[1].number = duplicate_sources.sources[0].number
    with pytest.raises(AppError, match="Source numbers"):
        report_service.persist_report(db_session, research_id, duplicate_sources)


def test_only_one_current_report_is_allowed(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    report_service.persist_report(db_session, research_id, report_payload())

    with pytest.raises(AppError) as error:
        report_service.persist_report(db_session, research_id, report_payload())

    assert error.value.status_code == 409
    assert error.value.code == "research_report_exists"


def test_hard_deleting_research_cascades_entire_evidence_graph(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    report_service.persist_report(db_session, research_id, report_payload())
    research = db_session.get(Research, research_id)
    assert research is not None

    db_session.delete(research)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(ResearchReport)) == 0
    assert db_session.scalar(select(func.count()).select_from(ReportSection)) == 0
    assert db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert db_session.scalar(select(func.count()).select_from(Citation)) == 0
