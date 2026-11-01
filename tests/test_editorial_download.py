import uuid

import pytest
from conftest import login
from sqlalchemy import select
from test_changes import PDF, details, submit

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import AuditEvent, EditorAssignment, Submission, SubmissionFile, User


@pytest.fixture
def manuscript(client):
    login(client)
    r = client.post("/api/v1/author/submissions", json=details())
    assert r.status_code == 201
    sid = uuid.UUID(r.json()["id"])
    r = client.post(
        f"/api/v1/author/submissions/{sid}/files",
        files={"upload": ("paper.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201
    assert submit(client, str(sid)).status_code == 200
    with get_session_factory()() as db:
        chief = db.scalar(
            select(User).where(User.email == "editor_in_chief@example.test")
        )
        assignment = EditorAssignment(
            submission_id=sid, editor_id=chief.id, assigned_by_id=chief.id
        )
        db.add(assignment)
        file = db.scalar(
            select(SubmissionFile).where(SubmissionFile.submission_id == sid)
        )
        db.commit()
        return dict(
            submission=sid,
            file=file.id,
            assignment=assignment.id,
            url=f"/api/v1/editorial/submissions/{sid}/files/{file.id}",
            path=get_settings().private_storage_path / file.storage_name,
        )


def test_download_bytes_name_cache_and_audit(client, manuscript):
    login(client, "editor_in_chief")
    case = client.get(f"/api/v1/editorial/submissions/{manuscript['submission']}")
    assert case.json()["files"][0]["download_url"] == manuscript["url"]
    r = client.get(manuscript["url"])
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-disposition"] == 'attachment; filename="paper.pdf"'
    assert r.headers["cache-control"] == "private, no-store"
    with get_session_factory()() as db:
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "editorial.manuscript_downloaded"
            )
        )
        assert event.target_id == str(manuscript["file"])


@pytest.mark.parametrize(
    "role,code", [("author", 403), ("site_admin", 403), (None, 401)]
)
def test_roles(client, manuscript, role, code):
    if role:
        login(client, role)
    else:
        client.cookies.clear()
    assert client.get(manuscript["url"]).status_code == code


def test_revoked_assignment(client, manuscript):
    login(client, "editor_in_chief")
    with get_session_factory()() as db:
        db.get(EditorAssignment, manuscript["assignment"]).is_active = False
        db.commit()
    assert client.get(manuscript["url"]).status_code == 404


@pytest.mark.parametrize("scan_status", ["pending", "infected", "scan_failed"])
def test_scanning(client, manuscript, scan_status):
    login(client, "editor_in_chief")
    with get_session_factory()() as db:
        db.get(SubmissionFile, manuscript["file"]).scan_status = scan_status
        db.commit()
    case = client.get(f"/api/v1/editorial/submissions/{manuscript['submission']}")
    assert case.json()["files"][0]["download_url"] is None
    assert client.get(manuscript["url"]).status_code == 423


def test_cross_case(client, manuscript):
    login(client, "editor_in_chief")
    with get_session_factory()() as db:
        source = db.get(Submission, manuscript["submission"])
        assignment = db.get(EditorAssignment, manuscript["assignment"])
        other = Submission(
            reference="NSAJ-OTHER",
            submitting_author_id=source.submitting_author_id,
            title="Other case",
            status="submitted",
        )
        db.add(other)
        db.flush()
        db.add(
            EditorAssignment(
                submission_id=other.id,
                editor_id=assignment.editor_id,
                assigned_by_id=assignment.assigned_by_id,
            )
        )
        db.commit()
        url = f"/api/v1/editorial/submissions/{other.id}/files/{manuscript['file']}"
    assert client.get(url).status_code == 404


def test_missing_storage(client, manuscript):
    login(client, "editor_in_chief")
    manuscript["path"].unlink()
    assert client.get(manuscript["url"]).status_code == 404
