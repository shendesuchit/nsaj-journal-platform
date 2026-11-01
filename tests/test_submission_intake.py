import re
import uuid

import pytest
from sqlalchemy import select
from test_editorial_publication import (
    add_clean_file,
    authenticate,
    seed_submission,
    seed_user,
)

from app.core.config import get_settings
from app.models import AuditEvent, Submission, SubmissionFile, SubmissionReceipt


def approve(client, secret):
    token = authenticate(client, "chief@intake.test", secret=secret)
    headers = {"X-CSRF-Token": token}
    response = client.post(
        "/api/v1/editorial/submission-checklists",
        json={
            "title": "Approved test checklist",
            "declarations": ["Test declaration A", "Test declaration B"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    checklist = response.json()["id"]
    assert (
        client.post(
            f"/api/v1/editorial/submission-checklists/{checklist}/approve",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/editorial/submission-checklists/{checklist}/approve",
            headers=headers,
        ).status_code
        == 409
    )
    return checklist


@pytest.mark.parametrize("generated_reference", [True, False])
def test_submission_handoff_and_immutable_receipt(
    client, session_factory, generated_reference
):
    author, _ = seed_user(session_factory, "author@intake.test", "author")
    _, secret = seed_user(
        session_factory, "chief@intake.test", "editor_in_chief", mfa=True
    )
    if generated_reference:
        token = authenticate(client, "author@intake.test")
        created = client.post(
            "/api/v1/author/submissions",
            json={
                "title": "A private scientific study",
                "abstract": "Complete abstract",
                "keywords": ["science"],
                "manuscript_type": "original research",
                "discipline": "science",
                "authors": [{"full_name": "Author", "affiliation": "Institute"}],
            },
            headers={"X-CSRF-Token": token},
        )
        assert created.status_code == 201
        submission = uuid.UUID(created.json()["id"])
        prefix = re.escape(get_settings().manuscript_id_prefix)
        assert re.fullmatch(rf"{prefix}-\d{{8}}", created.json()["reference"])
        with session_factory() as db:
            add_clean_file(db, submission)
            db.commit()
    else:
        submission, _ = seed_submission(session_factory, author, "draft")
    with session_factory() as db:
        reference = db.get(Submission, submission).reference
    checklist = approve(client, secret)
    token = authenticate(client, "author@intake.test")
    headers = {"X-CSRF-Token": token}
    url = f"/api/v1/author/submissions/{submission}/submit"
    payload = {"checklist_id": checklist, "acknowledged_indices": [0, 1]}
    assert client.post(url, json=payload).status_code == 403
    for indices in ([], [0], [0, 0], [0, 1, 2]):
        assert (
            client.post(
                url, json={**payload, "acknowledged_indices": indices}, headers=headers
            ).status_code
            == 422
        )
    assert (
        client.post(
            url, json={**payload, "checklist_id": str(uuid.uuid4())}, headers=headers
        ).status_code
        == 409
    )
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submitted"
    assert response.json()["reference"] == reference
    assert client.post(url, json=payload, headers=headers).status_code == 409
    assert client.get("/api/v1/author/submissions").json()["items"] == []
    assert (
        client.patch(
            f"/api/v1/author/submissions/{submission}", json={}, headers=headers
        ).status_code
        == 409
    )
    receipt_url = f"/api/v1/author/submissions/{submission}/receipt"
    original_receipt = client.get(receipt_url).json()
    assert original_receipt["reference"] == reference
    assert original_receipt["declarations"] == [
        "Test declaration A",
        "Test declaration B",
    ]
    with session_factory() as db:
        receipt = db.get(SubmissionReceipt, submission)
        assert receipt.manuscript_snapshot["title"] == "A private scientific study"
        assert receipt.manuscript_snapshot["reference"] == reference
        assert db.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "submission.submitted")
        )
        if not generated_reference:
            # Receipts saved before paper IDs were included still expose the
            # existing reference without rewriting their historical snapshot.
            receipt.manuscript_snapshot = {
                key: value
                for key, value in receipt.manuscript_snapshot.items()
                if key != "reference"
            }
            db.commit()
    assert client.get(receipt_url).json() == original_receipt
    authenticate(client, "chief@intake.test", secret=secret)
    assert str(submission) in {
        item["id"]
        for item in client.get("/api/v1/editorial/unassigned").json()["items"]
    }
    assert client.get("/api/v1/editorial/unassigned").json()["items"][0][
        "reference"
    ] == reference
    approve(client, secret)
    authenticate(client, "author@intake.test")
    assert client.get(receipt_url).json() == original_receipt
    seed_user(session_factory, "other@intake.test", "author")
    token = authenticate(client, "other@intake.test")
    assert client.get(receipt_url).status_code == 404
    assert (
        client.post(url, json=payload, headers={"X-CSRF-Token": token}).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/author/submissions/{submission}/editorial").status_code
        == 404
    )


def test_submission_validation_and_policy_access(client, session_factory):
    assert client.get("/api/v1/author/submission-checklist").status_code == 401
    author, _ = seed_user(session_factory, "author@intake.test", "author")
    _, secret = seed_user(
        session_factory, "chief@intake.test", "editor_in_chief", mfa=True
    )
    submission, file_id = seed_submission(session_factory, author, "draft")
    token = authenticate(client, "author@intake.test")
    checklist_response = client.get("/api/v1/author/submission-checklist").json()
    assert checklist_response["checklist"]["title"] == "Author declarations"
    assert client.get("/api/v1/editorial/submission-checklists").status_code == 403
    payload = {"checklist_id": str(uuid.uuid4()), "acknowledged_indices": [0, 1]}
    url = f"/api/v1/author/submissions/{submission}/submit"
    assert (
        client.post(url, json=payload, headers={"X-CSRF-Token": token}).status_code
        == 409
    )
    checklist = approve(client, secret)
    token = authenticate(client, "author@intake.test")
    headers = {"X-CSRF-Token": token}
    payload["checklist_id"] = checklist
    with session_factory() as db:
        item = db.get(Submission, submission)
        item.abstract = " "
        db.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 422
    with session_factory() as db:
        db.get(Submission, submission).abstract = "Complete abstract"
        db.get(SubmissionFile, file_id).scan_status = "quarantined"
        db.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 423
    with session_factory() as db:
        item = db.get(SubmissionFile, file_id)
        item.scan_status = "clean"
        item.storage_name = "missing.pdf"
        db.commit()
    assert client.post(url, json=payload, headers=headers).status_code == 423
    for role in ("reviewer", "site_admin"):
        _, role_secret = seed_user(
            session_factory, f"{role}@intake.test", role, mfa=role == "site_admin"
        )
        role_token = authenticate(client, f"{role}@intake.test", secret=role_secret)
        assert client.get("/api/v1/editorial/submission-checklists").status_code == 403
        assert (
            client.post(
                "/api/v1/editorial/submission-checklists",
                json={"title": "X", "declarations": ["X"]},
                headers={"X-CSRF-Token": role_token},
            ).status_code
            == 403
        )
