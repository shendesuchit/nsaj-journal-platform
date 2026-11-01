import uuid
from datetime import UTC, datetime

from conftest import login
from sqlalchemy import select

from app.models import AuditEvent, Issue


def test_volume_lifecycle_preserves_public_archive(client, session_factory):
    login(client, "site_admin")
    volume = client.post(
        "/api/v1/admin/volumes", json={"number": 9, "year": 2026}
    ).json()["id"]
    issue = client.post(
        "/api/v1/admin/issues", json={"volume_id": volume, "number": "1"}
    ).json()["id"]
    path = f"/api/v1/admin/volumes/{volume}/status"

    def change(previous, target):
        return client.put(path, json={"expected_status": previous, "status": target})

    assert change("open", "archived").status_code == 409
    assert change("open", "closed").status_code == 200
    assert change("open", "closed").status_code == 409
    assert (
        client.post(
            "/api/v1/admin/issues", json={"volume_id": volume, "number": "2"}
        ).status_code
        == 409
    )
    assert change("closed", "archived").status_code == 409
    with session_factory() as db:
        record = db.get(Issue, uuid.UUID(issue))
        record.status = "published"
        record.published_at = datetime.now(UTC)
        db.commit()
    assert change("closed", "archived").status_code == 200
    public = client.get("/api/v1/public/issues").json()
    assert issue in {item["id"] for item in public["items"]}
    assert change("archived", "open").status_code == 409
    assert change("archived", "closed").status_code == 200
    assert change("closed", "open").status_code == 200
    with session_factory() as db:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "publication.volume_status_changed",
                AuditEvent.target_id == volume,
            )
        ).all()
        assert len(events) == 4
    assert client.put(path, json={"status": "invalid"}).status_code == 422
    login(client, "author")
    assert change("open", "closed").status_code == 403
    client.cookies.clear()
    assert change("open", "closed").status_code in {401, 403}
