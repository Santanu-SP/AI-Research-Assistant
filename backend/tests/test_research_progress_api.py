from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.states import ProjectStatus
from app.services import research as research_service

PROGRESS_PATH = "/api/v1/research/{research_id}/status"
STEP_IDS = [
    "planning",
    "searching_sources",
    "finding_documents",
    "reviewing_evidence",
    "building_synthesis",
]
STEP_TITLES = [
    "Planning research",
    "Searching sources",
    "Finding relevant uploaded documents",
    "Reviewing evidence",
    "Building synthesis",
]


def create_research(client: TestClient) -> UUID:
    response = client.post(
        "/api/v1/research",
        json={"question": "How should research progress be represented?"},
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def get_progress(client: TestClient, research_id: UUID) -> dict[str, object]:
    response = client.get(PROGRESS_PATH.format(research_id=research_id))
    assert response.status_code == 200, response.text
    return response.json()


def assert_utc_timestamp(value: object) -> None:
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None


def test_draft_progress_response_is_factual_and_frontend_friendly(
    client: TestClient,
) -> None:
    research_id = create_research(client)

    body = get_progress(client, research_id)

    assert set(body) == {
        "id",
        "question",
        "status",
        "researchDepth",
        "currentStage",
        "currentStepIndex",
        "totalSteps",
        "steps",
        "sourcesDiscovered",
        "sourcesReviewed",
        "documentsFound",
        "startedAt",
        "stageStartedAt",
        "updatedAt",
        "completedAt",
        "failedAt",
    }
    assert body["id"] == str(research_id)
    assert body["status"] == "draft"
    assert body["researchDepth"] == "standard"
    assert body["currentStage"] is None
    assert body["currentStepIndex"] is None
    assert body["totalSteps"] == 5
    assert [step["id"] for step in body["steps"]] == STEP_IDS
    assert [step["title"] for step in body["steps"]] == STEP_TITLES
    assert [step["status"] for step in body["steps"]] == ["pending"] * 5
    assert body["sourcesDiscovered"] == 0
    assert body["sourcesReviewed"] == 0
    assert body["documentsFound"] == 0
    assert body["startedAt"] is None
    assert body["stageStartedAt"] is None
    assert body["completedAt"] is None
    assert body["failedAt"] is None
    assert_utc_timestamp(body["updatedAt"])


def test_progress_response_does_not_fabricate_execution_data(
    client: TestClient,
) -> None:
    research_id = create_research(client)

    body = get_progress(client, research_id)

    forbidden_fields = {
        "progress",
        "progressPercentage",
        "estimatedCompletionTime",
        "sources",
        "evidence",
        "citations",
        "output",
        "reasoning",
        "dossierId",
    }
    assert forbidden_fields.isdisjoint(body)


def test_missing_and_archived_research_progress_return_404(
    client: TestClient,
) -> None:
    missing = client.get(PROGRESS_PATH.format(research_id=uuid4()))
    research_id = create_research(client)
    archived = client.delete(f"/api/v1/research/{research_id}")
    hidden = client.get(PROGRESS_PATH.format(research_id=research_id))

    assert missing.status_code == 404
    assert archived.status_code == 204
    assert hidden.status_code == 404


def test_trusted_start_persists_planning_state_and_utc_timestamps(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)

    research_service.start_research(db_session, research_id)
    body = get_progress(client, research_id)

    assert body["status"] == "researching"
    assert body["currentStage"] == "planning"
    assert body["currentStepIndex"] == 0
    assert [step["status"] for step in body["steps"]] == [
        "active",
        "pending",
        "pending",
        "pending",
        "pending",
    ]
    assert_utc_timestamp(body["startedAt"])
    assert_utc_timestamp(body["stageStartedAt"])


@pytest.mark.parametrize(
    ("project_status", "expected_stage", "expected_index"),
    [
        (ProjectStatus.PAPERS_DISCOVERED, "searching_sources", 1),
        (ProjectStatus.PAPERS_SELECTED, "finding_documents", 2),
        (ProjectStatus.PROCESSING, "finding_documents", 2),
        (ProjectStatus.RESEARCH_READY, "reviewing_evidence", 3),
        (ProjectStatus.ANALYZING, "reviewing_evidence", 3),
        (ProjectStatus.REVIEW_READY, "building_synthesis", 4),
    ],
)
def test_project_status_maps_to_stable_frontend_progress(
    client: TestClient,
    db_session: Session,
    project_status: ProjectStatus,
    expected_stage: str,
    expected_index: int,
) -> None:
    research_id = create_research(client)
    research_service.start_research(db_session, research_id)

    research_service.update_research_lifecycle(
        db_session,
        research_id,
        project_status,
    )
    body = get_progress(client, research_id)

    assert body["status"] == "researching"
    assert body["currentStage"] == expected_stage
    assert body["currentStepIndex"] == expected_index
    assert [step["status"] for step in body["steps"]] == (
        ["completed"] * expected_index
        + ["active"]
        + ["pending"] * (4 - expected_index)
    )


def test_completion_marks_every_step_complete(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    research_service.start_research(db_session, research_id)

    research_service.mark_research_completed(db_session, research_id)
    body = get_progress(client, research_id)

    assert body["status"] == "completed"
    assert body["currentStage"] == "building_synthesis"
    assert body["currentStepIndex"] == 4
    assert [step["status"] for step in body["steps"]] == ["completed"] * 5
    assert_utc_timestamp(body["completedAt"])
    assert body["failedAt"] is None


def test_failure_retains_last_stage_and_marks_only_that_step_failed(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    research_service.start_research(db_session, research_id)
    research_service.update_research_lifecycle(
        db_session,
        research_id,
        ProjectStatus.ANALYZING,
    )

    research_service.mark_research_failed(db_session, research_id)
    body = get_progress(client, research_id)

    assert body["status"] == "failed"
    assert body["currentStage"] == "reviewing_evidence"
    assert body["currentStepIndex"] == 3
    assert [step["status"] for step in body["steps"]] == [
        "completed",
        "completed",
        "completed",
        "failed",
        "pending",
    ]
    assert body["completedAt"] is None
    assert_utc_timestamp(body["failedAt"])


def test_trusted_count_update_is_exposed_by_status_endpoint(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)

    research_service.update_progress_counts(
        db_session,
        research_id,
        sources_discovered=8,
        sources_reviewed=5,
        documents_found=3,
    )
    body = get_progress(client, research_id)

    assert body["sourcesDiscovered"] == 8
    assert body["sourcesReviewed"] == 5
    assert body["documentsFound"] == 3


@pytest.mark.parametrize(
    "counts",
    [
        {"sources_discovered": -1},
        {"sources_reviewed": -1},
        {"documents_found": -1},
        {"sources_discovered": 1, "sources_reviewed": 2},
        {},
    ],
)
def test_trusted_count_update_rejects_invalid_values(
    client: TestClient,
    db_session: Session,
    counts: dict[str, int],
) -> None:
    research_id = create_research(client)

    with pytest.raises(AppError) as exc_info:
        research_service.update_progress_counts(db_session, research_id, **counts)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_research_progress_counts"
    body = get_progress(client, research_id)
    assert body["sourcesDiscovered"] == 0
    assert body["sourcesReviewed"] == 0
    assert body["documentsFound"] == 0


def test_database_enforces_progress_count_constraints(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)
    research = research_service.get_research(db_session, research_id)
    research.sources_reviewed = 1

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_lifecycle_updates_require_start_and_start_is_idempotence_safe(
    client: TestClient,
    db_session: Session,
) -> None:
    research_id = create_research(client)

    with pytest.raises(AppError) as not_started:
        research_service.update_research_lifecycle(
            db_session,
            research_id,
            ProjectStatus.PAPERS_DISCOVERED,
        )
    assert not_started.value.status_code == 409
    assert not_started.value.code == "research_not_started"

    research_service.start_research(db_session, research_id)
    with pytest.raises(AppError) as already_started:
        research_service.start_research(db_session, research_id)
    assert already_started.value.status_code == 409
    assert already_started.value.code == "research_already_started"
