from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_editorial_publication import authenticate, seed_user

from app.models import (
    EditorialBoardProfile,
    PublicPageHistory,
    TemplateResource,
    User,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}


def test_public_page_keeps_last_approved_version_while_edits_are_draft(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin_id, secret = seed_user(
        session_factory, "content-pages-admin@example.test", "site_admin", mfa=True
    )
    csrf = authenticate(client, "content-pages-admin@example.test", secret=secret)
    created = client.post(
        "/api/v1/admin/pages",
        json={
            "slug": "aims-and-scope",
            "title": "Aims and scope",
            "body": "Approved public text.",
        },
        headers=headers(csrf),
    )
    assert created.status_code == 201, created.text
    assert client.get("/api/v1/public/pages/aims-and-scope").status_code == 404
    published = client.post(
        "/api/v1/admin/pages/aims-and-scope/publish", headers=headers(csrf)
    )
    assert published.status_code == 200
    updated = client.put(
        "/api/v1/admin/pages/aims-and-scope",
        json={
            "slug": "aims-and-scope",
            "title": "Updated aims",
            "body": "New draft text.",
        },
        headers=headers(csrf),
    )
    assert updated.status_code == 200
    public = client.get("/api/v1/public/pages/aims-and-scope")
    assert public.status_code == 200
    assert public.json()["body"] == "Approved public text."
    with session_factory() as db:
        versions = db.scalars(
            select(PublicPageHistory).order_by(PublicPageHistory.version)
        ).all()
        assert [item.status for item in versions] == [
            "draft",
            "published",
            "published",
            "draft",
        ][: len(versions)]
        assert db.get(User, admin_id) is not None


def test_calls_announcements_board_consent_and_template_scan_gate(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    admin_id, secret = seed_user(
        session_factory, "content-admin@example.test", "site_admin", mfa=True
    )
    csrf = authenticate(client, "content-admin@example.test", secret=secret)

    call = client.post(
        "/api/v1/admin/calls-for-papers",
        json={
            "title": "A sample call",
            "description": "Approved call description.",
            "scope": "Science and engineering.",
            "manuscript_types": ["original research"],
            "instructions": "Use the submission workspace.",
            "related_issue_id": None,
            "opens_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
            "deadline_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
            "time_zone": "UTC",
            "contact": "",
            "display_order": 0,
        },
        headers=headers(csrf),
    )
    assert call.status_code == 201, call.text
    call_id = call.json()["id"]
    approved_call = client.post(
        f"/api/v1/admin/calls-for-papers/{call_id}/approve",
        json={"status": "open"},
        headers=headers(csrf),
    )
    assert approved_call.status_code == 200
    call_public = client.get("/api/v1/public/calls-for-papers")
    assert call_public.status_code == 200
    assert call_public.json()["items"][0]["status"] == "open"

    announcement = client.post(
        "/api/v1/admin/announcements",
        json={
            "title": "A public notice",
            "body": "Approved notice.",
            "publish_at": None,
        },
        headers=headers(csrf),
    )
    assert announcement.status_code == 201
    assert client.get("/api/v1/public/announcements").json()["items"] == []
    published_announcement = client.post(
        f"/api/v1/admin/announcements/{announcement.json()['id']}/publish",
        headers=headers(csrf),
    )
    assert published_announcement.status_code == 200
    assert (
        client.get("/api/v1/public/announcements").json()["items"][0]["title"]
        == "A public notice"
    )

    board = client.post(
        "/api/v1/admin/board",
        json={
            "full_name": "Verified Editor",
            "role": "board_member",
            "qualifications": "PhD",
            "department": "Science",
            "institution": "Example Institute",
            "country": "Example",
            "specializations": ["physics"],
            "biography": "Approved biography.",
            "professional_url": None,
            "orcid": None,
            "professional_email": None,
            "appointment_start": None,
            "appointment_end": None,
            "display_order": 0,
        },
        headers=headers(csrf),
    )
    assert board.status_code == 201
    profile_id = board.json()["id"]
    assert client.get("/api/v1/public/editorial-board").json()["items"] == []
    not_verified = client.post(
        f"/api/v1/admin/board/{profile_id}/publish",
        json={"public_approved": True},
        headers=headers(csrf),
    )
    assert not_verified.status_code == 409
    verified = client.post(
        f"/api/v1/admin/board/{profile_id}/verification",
        json={
            "identity_verified": True,
            "qualification_verified": True,
            "affiliation_verified": True,
            "appointment_confirmed": True,
            "consent_status": "granted",
            "consent_evidence_reference": "consent-form-reference",
            "public_fields": ["full_name", "role", "institution"],
        },
        headers=headers(csrf),
    )
    assert verified.status_code == 200
    approved_profile = client.post(
        f"/api/v1/admin/board/{profile_id}/publish",
        json={"public_approved": True},
        headers=headers(csrf),
    )
    assert approved_profile.status_code == 200
    board_public = client.get("/api/v1/public/editorial-board").json()["items"]
    assert board_public == [
        {
            "id": profile_id,
            "full_name": "Verified Editor",
            "role": "board_member",
            "institution": "Example Institute",
        }
    ]

    monkeypatch.setattr(
        "app.services.private_files.scan_with_defender", lambda _: "unavailable"
    )
    template = client.post(
        "/api/v1/admin/templates",
        data={
            "title": "Private form",
            "category": "author form",
            "description": "Draft",
            "language": "en",
            "version": "1.0",
        },
        files={"upload": ("form.pdf", PDF_BYTES, "application/pdf")},
        headers=headers(csrf),
    )
    assert template.status_code == 201, template.text
    template_id = template.json()["id"]
    assert template.json()["scan_status"] == "unavailable"
    blocked = client.post(
        f"/api/v1/admin/templates/{template_id}/publish", headers=headers(csrf)
    )
    assert blocked.status_code == 423
    assert client.get("/api/v1/public/templates").json()["items"] == []
    resource_file = client.post(
        "/api/v1/admin/resources",
        files={"upload": ("presentation.pdf", PDF_BYTES, "application/pdf")},
        headers=headers(csrf),
    )
    assert resource_file.status_code == 201, resource_file.text
    presentation = client.post(
        "/api/v1/admin/presentations",
        json={
            "title": "Private presentation draft",
            "presenter": "",
            "resource_type": "presentation",
            "summary": "Awaiting malware scan.",
            "occurred_at": None,
            "external_url": None,
            "file_id": resource_file.json()["id"],
            "related_article_id": None,
            "related_issue_id": None,
            "display_order": 0,
        },
        headers=headers(csrf),
    )
    assert presentation.status_code == 201, presentation.text
    presentation_blocked = client.post(
        f"/api/v1/admin/presentations/{presentation.json()['id']}/publish",
        headers=headers(csrf),
    )
    assert presentation_blocked.status_code == 423
    assert client.get("/api/v1/public/presentations").json()["items"] == []
    with session_factory() as db:
        assert db.get(TemplateResource, uuid.UUID(template_id)).status == "draft"
        assert db.get(EditorialBoardProfile, uuid.UUID(profile_id)).public_approved
        assert db.get(User, admin_id) is not None


def test_clean_template_is_served_only_after_explicit_approval(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, secret = seed_user(
        session_factory, "clean-template-admin@example.test", "site_admin", mfa=True
    )
    csrf = authenticate(client, "clean-template-admin@example.test", secret=secret)
    uploaded = client.post(
        "/api/v1/admin/templates",
        data={
            "title": "Manuscript template",
            "category": "manuscript",
            "description": "Verified template",
            "language": "en",
            "version": "1",
        },
        files={"upload": ("template.pdf", PDF_BYTES, "application/pdf")},
        headers=headers(csrf),
    )
    assert uploaded.status_code == 201, uploaded.text
    template_id = uploaded.json()["id"]
    assert client.get("/api/v1/public/templates").json()["items"] == []
    published = client.post(
        f"/api/v1/admin/templates/{template_id}/publish", headers=headers(csrf)
    )
    assert published.status_code == 200
    public_templates = client.get("/api/v1/public/templates").json()["items"]
    assert public_templates[0]["title"] == "Manuscript template"
    download = client.get(f"/api/v1/public/templates/{template_id}/file")
    assert download.status_code == 200
    assert download.content == PDF_BYTES


def test_admin_content_lists_require_manager_and_include_editable_content(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch
) -> None:
    _, secret = seed_user(
        session_factory, "content-overview-admin@example.test", "site_admin", mfa=True
    )
    csrf = authenticate(client, "content-overview-admin@example.test", secret=secret)
    request_headers = headers(csrf)

    call = client.post(
        "/api/v1/admin/calls-for-papers",
        json={
            "title": "Overview call",
            "description": "Private draft description.",
            "scope": "Draft scope.",
            "manuscript_types": ["original research"],
            "instructions": "Draft instructions.",
            "opens_at": None,
            "deadline_at": None,
            "time_zone": "UTC",
            "contact": "private-contact@example.test",
        },
        headers=request_headers,
    )
    assert call.status_code == 201, call.text

    announcement = client.post(
        "/api/v1/admin/announcements",
        json={"title": "Overview announcement", "body": "Private draft notice."},
        headers=request_headers,
    )
    assert announcement.status_code == 201, announcement.text

    monkeypatch.setattr(
        "app.services.private_files.scan_with_defender", lambda _: "unavailable"
    )
    template = client.post(
        "/api/v1/admin/templates",
        data={
            "title": "Overview template",
            "category": "manuscript",
            "description": "Private template description.",
            "language": "en",
            "version": "1.0",
        },
        files={"upload": ("template.pdf", PDF_BYTES, "application/pdf")},
        headers=request_headers,
    )
    assert template.status_code == 201, template.text

    resource_file = client.post(
        "/api/v1/admin/resources",
        files={"upload": ("resource.pdf", PDF_BYTES, "application/pdf")},
        headers=request_headers,
    )
    assert resource_file.status_code == 201, resource_file.text
    presentation = client.post(
        "/api/v1/admin/presentations",
        json={
            "title": "Overview resource",
            "presenter": "Private presenter",
            "resource_type": "presentation",
            "summary": "Private summary.",
            "occurred_at": None,
            "external_url": None,
            "file_id": resource_file.json()["id"],
        },
        headers=request_headers,
    )
    assert presentation.status_code == 201, presentation.text

    calls = client.get("/api/v1/admin/calls-for-papers").json()["items"]
    assert len(calls) == 1
    assert calls[0]["id"] == call.json()["id"]
    assert calls[0]["status"] == "draft"
    assert calls[0]["description"] == "Private draft description."
    assert calls[0]["scope"] == "Draft scope."
    assert calls[0]["instructions"] == "Draft instructions."
    assert calls[0]["contact"] == "private-contact@example.test"

    announcements = client.get("/api/v1/admin/announcements").json()["items"]
    assert len(announcements) == 1
    assert announcements[0]["id"] == announcement.json()["id"]
    assert announcements[0]["status"] == "draft"
    assert announcements[0]["body"] == "Private draft notice."

    templates = client.get("/api/v1/admin/templates").json()["items"]
    assert templates == [
        {
            "id": template.json()["id"],
            "title": "Overview template",
            "category": "manuscript",
            "status": "draft",
            "scan_status": "unavailable",
        }
    ]

    resources = client.get("/api/v1/admin/presentations").json()["items"]
    assert resources == [
        {
            "id": presentation.json()["id"],
            "title": "Overview resource",
            "resource_type": "presentation",
            "status": "draft",
            "occurred_at": None,
            "has_external_url": False,
            "scan_status": "unavailable",
        }
    ]

    seed_user(session_factory, "content-overview-author@example.test", "author")
    client.cookies.clear()
    authenticate(client, "content-overview-author@example.test")
    for path in (
        "/api/v1/admin/calls-for-papers",
        "/api/v1/admin/announcements",
        "/api/v1/admin/templates",
        "/api/v1/admin/presentations",
    ):
        assert client.get(path).status_code == 403
