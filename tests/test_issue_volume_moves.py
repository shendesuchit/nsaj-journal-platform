from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_editorial_publication import authenticate, seed_user

from app.models import AuditEvent, Issue, Volume


def csrf_header(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def create_volume(client: TestClient, token: str, number: int, year: int) -> str:
    response = client.post(
        "/api/v1/admin/volumes",
        json={"number": number, "year": year, "title": f"Volume {number}"},
        headers=csrf_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_issue(
    client: TestClient, token: str, volume_id: str, number: str, title: str
) -> str:
    response = client.post(
        "/api/v1/admin/issues",
        json={
            "volume_id": volume_id,
            "number": number,
            "title": title,
            "description": (
                "Private working notes that must not appear in the board list."
            ),
        },
        headers=csrf_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_volume_issue_list_move_rules_and_public_filter(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    editor_id, secret = seed_user(
        session_factory, "volume-editor@example.test", "editor_in_chief", mfa=True
    )
    token = authenticate(client, "volume-editor@example.test", secret=secret)
    source_id = create_volume(client, token, 1, 2024)
    destination_id = create_volume(client, token, 2, 2025)
    closed_id = create_volume(client, token, 3, 2026)
    move_id = create_issue(client, token, source_id, "3", "Draft to move")
    duplicate_id = create_issue(client, token, source_id, "1", "Duplicate number draft")
    create_issue(client, token, destination_id, "1", "Existing destination issue")
    scheduled_id = create_issue(client, token, source_id, "4", "Scheduled issue")
    published_id = create_issue(client, token, source_id, "5", "Published issue")
    with session_factory() as db:
        db.get(Volume, uuid.UUID(closed_id)).status = "closed"
        db.get(Issue, uuid.UUID(scheduled_id)).status = "scheduled"
        published = db.get(Issue, uuid.UUID(published_id))
        published.status = "published"
        published.published_at = datetime.now(UTC)
        db.commit()

    listed = client.get("/api/v1/admin/volumes")
    assert listed.status_code == 200
    volumes = listed.json()["items"]
    assert [(item["number"], item["year"]) for item in volumes] == [
        (3, 2026),
        (2, 2025),
        (1, 2024),
    ]
    source = next(item for item in volumes if item["id"] == source_id)
    assert [item["number"] for item in source["issues"]] == ["3", "1", "4", "5"]
    draft_record = source["issues"][1]
    assert draft_record["status"] == "draft"
    assert "description" not in draft_record
    assert "articles" not in draft_record

    moved = client.put(
        f"/api/v1/admin/issues/{move_id}/volume",
        json={"volume_id": destination_id},
        headers=csrf_header(token),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json() == {
        "id": move_id,
        "volume_id": destination_id,
        "status": "draft",
        "unchanged": False,
    }
    same_volume = client.put(
        f"/api/v1/admin/issues/{move_id}/volume",
        json={"volume_id": destination_id},
        headers=csrf_header(token),
    )
    assert same_volume.status_code == 200
    assert same_volume.json()["unchanged"] is True

    duplicate = client.put(
        f"/api/v1/admin/issues/{duplicate_id}/volume",
        json={"volume_id": destination_id},
        headers=csrf_header(token),
    )
    assert duplicate.status_code == 409
    assert "Issue 1 already exists" in duplicate.json()["detail"]

    closed_destination = client.put(
        f"/api/v1/admin/issues/{duplicate_id}/volume",
        json={"volume_id": closed_id},
        headers=csrf_header(token),
    )
    assert closed_destination.status_code == 409
    assert "closed" in closed_destination.json()["detail"]

    for protected_issue_id in (scheduled_id, published_id):
        blocked = client.put(
            f"/api/v1/admin/issues/{protected_issue_id}/volume",
            json={"volume_id": destination_id},
            headers=csrf_header(token),
        )
        assert blocked.status_code == 409
        assert "Only draft issues" in blocked.json()["detail"]

    public_items = client.get("/api/v1/public/issues").json()["items"]
    assert [item["id"] for item in public_items] == [published_id]
    assert public_items[0]["volume"] == {"number": 1, "year": 2024}

    with session_factory() as db:
        moved_issue = db.get(Issue, uuid.UUID(move_id))
        assert moved_issue is not None and str(moved_issue.volume_id) == destination_id
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "publication.issue_moved")
        ).all()
        assert len(events) == 1
        assert events[0].actor_id == editor_id
        assert events[0].details["from_volume_id"] == source_id
        assert events[0].details["to_volume_id"] == destination_id

    author_id, _ = seed_user(session_factory, "volume-author@example.test", "author")
    del author_id
    author_token = authenticate(client, "volume-author@example.test")
    assert client.get("/api/v1/admin/volumes").status_code == 403
    denied = client.put(
        f"/api/v1/admin/issues/{move_id}/volume",
        json={"volume_id": source_id},
        headers=csrf_header(author_token),
    )
    assert denied.status_code == 403
