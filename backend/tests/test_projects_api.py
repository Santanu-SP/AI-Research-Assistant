from uuid import uuid4

from fastapi.testclient import TestClient


def create_project(
    client: TestClient,
    *,
    name: str = "Protein folding review",
    description: str | None = "Sources and questions for the review.",
) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": description},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_project_crud_search_pagination_and_archiving(client: TestClient) -> None:
    first = create_project(client)
    create_project(client, name="Battery materials", description=None)

    listed = client.get(
        "/api/v1/projects",
        params={"search": "protein", "limit": 1, "offset": 0},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == first["id"]

    updated = client.patch(
        f"/api/v1/projects/{first['id']}",
        json={"name": "Protein structure review", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Protein structure review"
    assert updated.json()["description"] is None

    archived = client.delete(f"/api/v1/projects/{first['id']}")
    assert archived.status_code == 204
    assert client.get(f"/api/v1/projects/{first['id']}").status_code == 404

    included = client.get(
        "/api/v1/projects",
        params={"includeArchived": "true"},
    ).json()
    assert included["total"] == 2
    assert any(item["archivedAt"] is not None for item in included["items"])


def test_project_validation_and_missing_project(client: TestClient) -> None:
    assert client.post("/api/v1/projects", json={"name": " "}).status_code == 422
    assert client.patch(f"/api/v1/projects/{uuid4()}", json={"name": "New"}).status_code == 404

    project = create_project(client)
    assert client.patch(f"/api/v1/projects/{project['id']}", json={}).status_code == 422
    assert client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": None}
    ).status_code == 422


def test_projects_are_private_to_the_authenticated_user(
    anonymous_client: TestClient,
) -> None:
    client = anonymous_client
    for name in ("Alice", "Bob"):
        assert client.post(
            "/api/v1/auth/register",
            json={
                "name": name,
                "email": f"{name.lower()}@example.com",
                "password": "long-password-123",
            },
        ).status_code == 201

    assert client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "long-password-123"},
    ).status_code == 200
    project = create_project(client, name="Alice private project")
    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "long-password-123"},
    ).status_code == 200
    assert client.get("/api/v1/projects").json()["total"] == 0
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"name": "Stolen"},
    ).status_code == 404
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 404


def test_archived_project_can_be_restored(client: TestClient) -> None:
    project = create_project(client)
    project_id = project["id"]

    # Only archived projects can be restored.
    assert client.post(f"/api/v1/projects/{project_id}/restore").status_code == 409

    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204
    restored = client.post(f"/api/v1/projects/{project_id}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["archivedAt"] is None
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200

    assert client.post(f"/api/v1/projects/{uuid4()}/restore").status_code == 404


def test_archived_project_can_be_deleted_and_keeps_its_files(
    client: TestClient,
) -> None:
    from tests.test_documents_api import PDF_MIME, make_pdf

    project = create_project(client)
    project_id = project["id"]
    upload = client.post(
        f"/api/v1/projects/{project_id}/documents",
        files={"file": ("kept.pdf", make_pdf("kept evidence"), PDF_MIME)},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    # An active project has to be archived first.
    assert client.delete(f"/api/v1/projects/{project_id}/permanent").status_code == 409

    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204
    deleted = client.delete(f"/api/v1/projects/{project_id}/permanent")
    assert deleted.status_code == 204

    listed = client.get(
        "/api/v1/projects", params={"includeArchived": "true"}
    ).json()
    assert all(item["id"] != project_id for item in listed["items"])
    assert client.post(f"/api/v1/projects/{project_id}/restore").status_code == 404

    document = client.get(f"/api/v1/documents/{document_id}")
    assert document.status_code == 200
    assert document.json()["projectId"] is None


def _add_research(client: TestClient, project_id: str, question: str) -> str:
    response = client.post(
        "/api/v1/research", json={"question": question, "projectId": project_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_project_list_counts_files_and_finished_reports(
    client: TestClient, test_app
) -> None:
    from uuid import UUID

    from sqlalchemy import event, update

    from app.core.time import utc_now
    from app.domain.research import ResearchStatus
    from app.models.research import Research
    from tests.test_documents_api import PDF_MIME, make_pdf

    busy = create_project(client, name="Busy project")
    empty = create_project(client, name="Empty project")
    for index in range(2):
        upload = client.post(
            f"/api/v1/projects/{busy['id']}/documents",
            files={"file": (f"f{index}.pdf", make_pdf(f"evidence {index}"), PDF_MIME)},
        )
        assert upload.status_code == 201, upload.text

    finished = _add_research(client, busy["id"], "What does the evidence show?")
    archived = _add_research(client, busy["id"], "What else does it show here?")
    _add_research(client, busy["id"], "A draft question that never ran")
    with test_app.state.db_session_factory() as session:
        session.execute(
            update(Research)
            .where(Research.id.in_([UUID(finished), UUID(archived)]))
            .values(status=ResearchStatus.COMPLETED)
        )
        session.execute(
            update(Research)
            .where(Research.id == UUID(archived))
            .values(archived_at=utc_now())
        )
        session.commit()

    statements: list[str] = []

    def count(conn, cursor, statement, *args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = test_app.state.db_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        listed = client.get("/api/v1/projects")
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert listed.status_code == 200
    by_name = {item["name"]: item for item in listed.json()["items"]}
    assert by_name["Busy project"]["fileCount"] == 2
    assert by_name["Busy project"]["reportCount"] == 1
    assert by_name["Empty project"]["fileCount"] == 0
    assert by_name["Empty project"]["reportCount"] == 0
    # The counts come from grouped queries, not one query per project.
    count_queries = [s for s in statements if "GROUP BY" in s.upper()]
    assert len(count_queries) == 2

    single = client.get(f"/api/v1/projects/{busy['id']}").json()
    assert single["fileCount"] == 2
    assert single["reportCount"] == 1
