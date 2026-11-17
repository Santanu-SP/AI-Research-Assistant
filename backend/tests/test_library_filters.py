from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.domain.documents import DocumentType
from app.models.document import Document
from tests.test_documents_api import PDF_MIME, make_pdf


def _upload(client: TestClient, name: str, text: str, project_id: str | None = None) -> dict:
    path = f"/api/v1/projects/{project_id}/documents" if project_id else "/api/v1/documents"
    response = client.post(
        path, files={"file": (name, make_pdf(text, title=None), PDF_MIME)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_library_can_be_filtered_by_kind_and_searched(
    client: TestClient, test_app
) -> None:
    report = _upload(client, "field-report.pdf", "field notes from the survey")
    photo = _upload(client, "whiteboard.pdf", "whiteboard photo text")
    with test_app.state.db_session_factory() as session:
        session.execute(
            update(Document)
            .where(Document.id == UUID(photo["id"]))
            .values(file_type=DocumentType.IMAGE)
        )
        session.commit()

    def names(**params: str) -> list[str]:
        response = client.get("/api/v1/documents", params=params)
        assert response.status_code == 200, response.text
        return sorted(item["name"] for item in response.json()["items"])

    assert names(kind="documents") == ["field-report.pdf"]
    assert names(kind="images") == ["whiteboard.pdf"]
    assert names(kind="links") == []
    assert names(search="FIELD") == ["field-report.pdf"]
    assert names(search="field", kind="images") == []
    assert client.get("/api/v1/documents", params={"kind": "spreadsheets"}).status_code == 422
    assert report["id"] != photo["id"]


def test_library_rows_say_where_each_file_is_used(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Thesis"}).json()
    used = _upload(client, "used.pdf", "evidence that is cited", project["id"])
    unused = _upload(client, "unused.pdf", "nothing points here")

    research = client.post(
        "/api/v1/research",
        json={
            "question": "What does the cited evidence show?",
            "title": "Cited evidence review",
            "projectId": project["id"],
            "documentIds": [used["id"]],
        },
    )
    assert research.status_code == 201, research.text

    items = {
        item["name"]: item
        for item in client.get("/api/v1/documents").json()["items"]
    }
    assert items["used.pdf"]["projectName"] == "Thesis"
    assert items["used.pdf"]["usedIn"] == [
        {"id": research.json()["id"], "title": "Cited evidence review"}
    ]
    assert items["used.pdf"]["usedInCount"] == 1
    assert items["unused.pdf"]["projectName"] is None
    assert items["unused.pdf"]["usedIn"] == []

    # Deleted research no longer counts as a place the file is used.
    assert client.delete(f"/api/v1/research/{research.json()['id']}").status_code == 204
    items = {
        item["name"]: item
        for item in client.get("/api/v1/documents").json()["items"]
    }
    assert items["used.pdf"]["usedIn"] == []
    assert unused["id"]
