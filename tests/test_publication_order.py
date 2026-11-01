from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from test_editorial_publication import authenticate, seed_user

from app.models import AuditEvent, Issue, Volume


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def _create_volume(client: TestClient, token: str, number: int, year: int) -> str:
    response = client.post(
        "/api/v1/admin/volumes",
        json={"number": number, "year": year, "title": f"Volume {number}"},
        headers=_csrf(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_issue(
    client: TestClient, token: str, volume_id: str, number: str
) -> str:
    response = client.post(
        "/api/v1/admin/issues",
        json={"volume_id": volume_id, "number": number, "title": f"Issue {number}"},
        headers=_csrf(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_editor_can_reorder_volumes_and_draft_issues_and_archive_uses_order(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    editor_id, secret = seed_user(
        session_factory, "order-editor@example.test", "editor_in_chief", mfa=True
    )
    token = authenticate(client, "order-editor@example.test", secret=secret)
    older_volume = _create_volume(client, token, 1, 2024)
    newer_volume = _create_volume(client, token, 2, 2025)

    older_published = _create_issue(client, token, older_volume, "1")
    newer_first_draft = _create_issue(client, token, newer_volume, "1")
    newer_published = _create_issue(client, token, newer_volume, "2")
    newer_second_draft = _create_issue(client, token, newer_volume, "3")
    with session_factory() as db:
        for issue_id in (older_published, newer_published):
            issue = db.get(Issue, uuid.UUID(issue_id))
            assert issue is not None
            issue.status = "published"
            issue.published_at = datetime(2026, 1, 1, tzinfo=UTC)
        db.commit()

    listed = client.get("/api/v1/admin/volumes")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [
        newer_volume,
        older_volume,
    ]
    assert [
        issue["display_order"]
        for item in listed.json()["items"]
        if item["id"] == newer_volume
        for issue in item["issues"]
    ] == [0, 1, 2]

    reorder_volumes = client.put(
        "/api/v1/admin/volumes/order",
        json={"volume_ids": [older_volume, newer_volume]},
        headers=_csrf(token),
    )
    assert reorder_volumes.status_code == 200, reorder_volumes.text
    reorder_drafts = client.put(
        f"/api/v1/admin/volumes/{newer_volume}/issues/order",
        json={"issue_ids": [newer_second_draft, newer_first_draft]},
        headers=_csrf(token),
    )
    assert reorder_drafts.status_code == 200, reorder_drafts.text

    listed = client.get("/api/v1/admin/volumes").json()["items"]
    assert [item["id"] for item in listed] == [older_volume, newer_volume]
    newer_issues = next(item for item in listed if item["id"] == newer_volume)["issues"]
    assert [item["id"] for item in newer_issues] == [
        newer_second_draft,
        newer_published,
        newer_first_draft,
    ]
    assert [item["number"] for item in newer_issues] == ["3", "2", "1"]

    public_issues = client.get("/api/v1/public/issues").json()["items"]
    assert [item["id"] for item in public_issues] == [
        older_published,
        newer_published,
    ]

    with session_factory() as db:
        events = db.query(AuditEvent).filter(
            AuditEvent.event_type.in_(
                [
                    "publication.volume_order_changed",
                    "publication.draft_issue_order_changed",
                ]
            )
        ).all()
        assert {event.event_type for event in events} == {
            "publication.volume_order_changed",
            "publication.draft_issue_order_changed",
        }
        assert all(event.actor_id == editor_id for event in events)
        assert db.get(Volume, uuid.UUID(older_volume)).display_order == 0


def test_order_endpoints_require_csrf_complete_membership_and_manager_role(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, manager_secret = seed_user(
        session_factory, "order-manager@example.test", "editor_in_chief", mfa=True
    )
    manager_token = authenticate(
        client, "order-manager@example.test", secret=manager_secret
    )
    volume_id = _create_volume(client, manager_token, 1, 2026)
    first_issue = _create_issue(client, manager_token, volume_id, "1")
    second_issue = _create_issue(client, manager_token, volume_id, "2")

    missing_csrf = client.put(
        "/api/v1/admin/volumes/order", json={"volume_ids": [volume_id]}
    )
    assert missing_csrf.status_code == 403

    incomplete_volumes = client.put(
        "/api/v1/admin/volumes/order",
        json={"volume_ids": []},
        headers=_csrf(manager_token),
    )
    assert incomplete_volumes.status_code == 409

    stale_issues = client.put(
        f"/api/v1/admin/volumes/{volume_id}/issues/order",
        json={"issue_ids": [first_issue]},
        headers=_csrf(manager_token),
    )
    assert stale_issues.status_code == 409

    seed_user(session_factory, "order-author@example.test", "author")
    author_token = authenticate(client, "order-author@example.test")
    forbidden = client.put(
        "/api/v1/admin/volumes/order",
        json={"volume_ids": [volume_id]},
        headers=_csrf(author_token),
    )
    assert forbidden.status_code == 403

    with session_factory() as db:
        assert db.get(Issue, uuid.UUID(first_issue)).display_order == 0
        assert db.get(Issue, uuid.UUID(second_issue)).display_order == 1
