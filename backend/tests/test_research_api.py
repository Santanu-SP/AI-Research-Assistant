from uuid import uuid4

from fastapi.testclient import TestClient


def create_research(
    client: TestClient,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {"question": "What makes evidence reliable?"}
    payload.update(overrides)
    response = client.post("/api/v1/research", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_research_with_all_supported_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research",
        json={
            "question": "  How should evidence be evaluated?  ",
            "title": "  Evaluating Evidence  ",
            "domain": "  Research Methods  ",
            "researchDepth": "deep",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Evaluating Evidence"
    assert body["question"] == "How should evidence be evaluated?"
    assert body["domain"] == "Research Methods"
    assert body["researchDepth"] == "deep"
    assert body["status"] == "draft"
    assert body["sourceCount"] == 0
    assert body["createdAt"].endswith("Z")
    assert body["updatedAt"].endswith("Z")
    assert body["archivedAt"] is None


def test_create_research_with_only_required_fields_uses_defaults(
    client: TestClient,
) -> None:
    body = create_research(client, question="How do citations support claims?")

    assert body["title"] == "How do citations support claims?"
    assert body["domain"] is None
    assert body["researchDepth"] == "standard"
    assert body["status"] == "draft"


def test_fallback_title_is_deterministic_and_shortened(client: TestClient) -> None:
    question = " ".join(["evidence"] * 20)

    first = create_research(client, question=question)
    second = create_research(client, question=question)

    assert first["title"] == second["title"]
    assert len(first["title"]) <= 80
    assert first["title"].endswith("...")


def test_empty_question_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/research", json={"question": "   "})

    assert response.status_code == 422


def test_blank_title_is_rejected_when_supplied(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research",
        json={"question": "Valid question", "title": "  "},
    )

    assert response.status_code == 422


def test_invalid_research_depth_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research",
        json={"question": "Valid question", "researchDepth": "extreme"},
    )

    assert response.status_code == 422


def test_list_research(client: TestClient) -> None:
    created = create_research(client, title="First record")

    response = client.get("/api/v1/research")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0]["id"] == created["id"]


def test_list_orders_by_most_recently_updated(client: TestClient) -> None:
    first = create_research(client, title="First")
    second = create_research(client, title="Second")
    update = client.patch(
        f"/api/v1/research/{first['id']}",
        json={"title": "First, updated"},
    )
    assert update.status_code == 200

    items = client.get("/api/v1/research").json()["items"]

    assert [item["id"] for item in items] == [first["id"], second["id"]]


def test_search_by_title(client: TestClient) -> None:
    matching = create_research(client, title="Reproducible experiments")
    create_research(client, title="Unrelated title")

    items = client.get("/api/v1/research", params={"search": "REPRODUCIBLE"}).json()[
        "items"
    ]

    assert [item["id"] for item in items] == [matching["id"]]


def test_search_by_question(client: TestClient) -> None:
    matching = create_research(
        client,
        question="How do protein structures change?",
        title="Biology",
    )
    create_research(client, question="How are markets regulated?", title="Economics")

    items = client.get("/api/v1/research", params={"search": "PROTEIN"}).json()[
        "items"
    ]

    assert [item["id"] for item in items] == [matching["id"]]


def test_filter_by_domain(client: TestClient) -> None:
    matching = create_research(client, domain="Biology")
    create_research(client, domain="Economics")

    items = client.get("/api/v1/research", params={"domain": "biology"}).json()[
        "items"
    ]

    assert [item["id"] for item in items] == [matching["id"]]


def test_filter_by_status_and_validate_status(client: TestClient) -> None:
    completed = create_research(client, title="Completed")
    create_research(client, title="Draft")
    update = client.patch(
        f"/api/v1/research/{completed['id']}",
        json={"status": "completed"},
    )
    assert update.status_code == 200

    filtered = client.get(
        "/api/v1/research",
        params={"status": "completed"},
    )
    invalid = client.get(
        "/api/v1/research",
        params={"status": "unknown"},
    )

    assert [item["id"] for item in filtered.json()["items"]] == [completed["id"]]
    assert invalid.status_code == 422


def test_pagination_with_limit_and_offset(client: TestClient) -> None:
    for title in ("First", "Second", "Third"):
        create_research(client, title=title)

    response = client.get(
        "/api/v1/research",
        params={"limit": 1, "offset": 1},
    )

    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1


def test_retrieve_one_research(client: TestClient) -> None:
    created = create_research(client)

    response = client.get(f"/api/v1/research/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_missing_research_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/research/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_not_found"


def test_update_title(client: TestClient) -> None:
    created = create_research(client, title="Original")

    response = client.patch(
        f"/api/v1/research/{created['id']}",
        json={"title": "  Updated title  "},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


def test_update_question_domain_and_depth(client: TestClient) -> None:
    created = create_research(client)

    response = client.patch(
        f"/api/v1/research/{created['id']}",
        json={
            "question": "  A revised question?  ",
            "domain": "  Computer Science  ",
            "researchDepth": "quick",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["question"] == "A revised question?"
    assert body["domain"] == "Computer Science"
    assert body["researchDepth"] == "quick"


def test_blank_update_and_empty_patch_are_rejected(client: TestClient) -> None:
    created = create_research(client)

    blank = client.patch(
        f"/api/v1/research/{created['id']}",
        json={"question": " "},
    )
    empty = client.patch(f"/api/v1/research/{created['id']}", json={})

    assert blank.status_code == 422
    assert empty.status_code == 422


def test_archive_research_and_exclude_it_from_normal_reads(
    client: TestClient,
) -> None:
    created = create_research(client)

    archived = client.delete(f"/api/v1/research/{created['id']}")
    retrieved = client.get(f"/api/v1/research/{created['id']}")
    normal_list = client.get("/api/v1/research").json()

    assert archived.status_code == 204
    assert retrieved.status_code == 404
    assert normal_list["total"] == 0
    assert normal_list["items"] == []


def test_include_archived_returns_archived_records(client: TestClient) -> None:
    created = create_research(client)
    response = client.delete(f"/api/v1/research/{created['id']}")
    assert response.status_code == 204

    included = client.get(
        "/api/v1/research",
        params={"includeArchived": "true"},
    ).json()

    assert included["total"] == 1
    assert included["items"][0]["id"] == created["id"]
    assert included["items"][0]["archivedAt"] is not None
