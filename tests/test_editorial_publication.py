from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import (
    Article,
    ArticleScholarlyAction,
    AuditEvent,
    EditorAssignment,
    EditorialDecision,
    Invitation,
    Issue,
    MfaRecoveryCode,
    ReviewAssignment,
    ReviewerProfile,
    Role,
    Submission,
    SubmissionAuthor,
    SubmissionFile,
    SubmissionRevision,
    User,
    UserMfa,
)
from app.services.security import (
    encrypt_totp_secret,
    hash_password,
    hash_secret,
    new_recovery_codes,
    new_totp_secret,
    totp_code,
)

PASSWORD = "test journal password 2026"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def seed_user(
    factory: sessionmaker[Session], email: str, role_name: str, *, mfa: bool = False
) -> tuple[uuid.UUID, str | None]:
    with factory() as db:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name)
            db.add(role)
            db.flush()
        user = User(
            email=email,
            display_name=email.split("@", 1)[0],
            password_hash=hash_password(PASSWORD),
            roles=[role],
        )
        secret = new_totp_secret() if mfa else None
        if secret:
            user.mfa = UserMfa(
                encrypted_totp_secret=encrypt_totp_secret(secret),
                enabled=True,
                recovery_codes=[
                    MfaRecoveryCode(code_hash=hash_secret(code))
                    for code in new_recovery_codes()
                ],
            )
        db.add(user)
        db.commit()
        return user.id, secret


def authenticate(client: TestClient, email: str, *, secret: str | None = None) -> str:
    csrf_token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    if secret:
        verified = client.post(
            "/api/v1/auth/mfa/verify",
            json={"code": totp_code(secret)},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert verified.status_code == 200, verified.text
        return payload["csrf_token"]
    return payload["csrf_token"]


def add_clean_file(
    db: Session, submission_id: uuid.UUID, name: str = "review.pdf"
) -> SubmissionFile:
    settings = get_settings()
    root = settings.private_storage_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(PDF_BYTES)
    record = SubmissionFile(
        submission_id=submission_id,
        storage_name=name,
        original_name=name,
        media_type="application/pdf",
        size_bytes=len(PDF_BYTES),
        sha256="a" * 64,
        scan_status="clean",
    )
    db.add(record)
    db.flush()
    return record


def seed_submission(
    factory: sessionmaker[Session],
    author_id: uuid.UUID,
    status: str,
    *,
    editor_id: uuid.UUID | None = None,
    file_name: str = "review.pdf",
) -> tuple[uuid.UUID, uuid.UUID]:
    with factory() as db:
        submission = Submission(
            reference=f"NSAJ-{uuid.uuid4().hex[:8].upper()}",
            submitting_author_id=author_id,
            status=status,
            title="A private scientific study",
            abstract="A confidential abstract for an editorial workflow test.",
            keywords=["science", "test"],
            manuscript_type="original research",
            discipline="science",
            authors=[
                SubmissionAuthor(
                    position=0,
                    full_name="Submitting Author",
                    affiliation="Example Institute",
                    email="author@example.test",
                )
            ],
        )
        db.add(submission)
        db.flush()
        manuscript_file = add_clean_file(db, submission.id, file_name)
        if editor_id:
            db.add(
                EditorAssignment(
                    submission_id=submission.id,
                    editor_id=editor_id,
                    assigned_by_id=editor_id,
                    can_make_decisions=True,
                    is_active=True,
                )
            )
        db.commit()
        return submission.id, manuscript_file.id


def csrf_header(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def test_editorial_case_offers_only_active_unassigned_reviewer_accounts(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "review-options-author@example.test", "author"
    )
    editor_id, editor_secret = seed_user(
        session_factory,
        "review-options-editor@example.test",
        "editor_in_chief",
        mfa=True,
    )
    assigned_reviewer_id, _ = seed_user(
        session_factory, "already-assigned@example.test", "reviewer"
    )
    available_reviewer_id, _ = seed_user(
        session_factory, "available-reviewer@example.test", "reviewer"
    )
    inactive_reviewer_id, _ = seed_user(
        session_factory, "inactive-reviewer@example.test", "reviewer"
    )
    submission_id, file_id = seed_submission(
        session_factory, author_id, "editorial_screening", editor_id=editor_id
    )
    with session_factory() as db:
        assigned_profile = ReviewerProfile(
            email="already-assigned@example.test",
            full_name="Already Assigned",
            user_id=assigned_reviewer_id,
        )
        available_profile = ReviewerProfile(
            email="available-reviewer@example.test",
            full_name="Available Reviewer",
            affiliation="Review Institute",
            expertise=["science"],
            languages=["English"],
            user_id=available_reviewer_id,
        )
        inactive_profile = ReviewerProfile(
            email="inactive-reviewer@example.test",
            full_name="Inactive Reviewer",
            user_id=inactive_reviewer_id,
        )
        db.add_all([assigned_profile, available_profile, inactive_profile])
        db.flush()
        db.get(User, inactive_reviewer_id).is_active = False
        db.add(
            ReviewAssignment(
                submission_id=submission_id,
                reviewer_profile_id=assigned_profile.id,
                reviewer_user_id=assigned_reviewer_id,
                manuscript_file_id=file_id,
                invited_by_id=editor_id,
                round_number=1,
            )
        )
        db.commit()

    authenticate(client, "review-options-editor@example.test", secret=editor_secret)
    response = client.get(f"/api/v1/editorial/submissions/{submission_id}")
    assert response.status_code == 200, response.text
    assert response.json()["reviewer_options"] == [
        {
            "id": str(available_profile.id),
            "full_name": "Available Reviewer",
            "email": "available-reviewer@example.test",
            "affiliation": "Review Institute",
            "expertise": ["science"],
            "languages": ["English"],
        }
    ]

    author_client = TestClient(client.app, raise_server_exceptions=False)
    try:
        authenticate(author_client, "review-options-author@example.test")
        denied = author_client.get(f"/api/v1/editorial/submissions/{submission_id}")
        assert denied.status_code == 403
    finally:
        author_client.close()


def test_production_article_picker_is_scoped_to_the_assigned_editor(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "article-choice-author@example.test", "author"
    )
    editor_id, editor_secret = seed_user(
        session_factory,
        "article-choice-editor@example.test",
        "editor_in_chief",
        mfa=True,
    )
    assigned_submission_id, _ = seed_submission(
        session_factory, author_id, "production", editor_id=editor_id
    )
    unassigned_submission_id, _ = seed_submission(
        session_factory,
        author_id,
        "production",
        file_name="article-choice-unassigned.pdf",
    )
    with session_factory() as db:
        db.add_all(
            [
                Article(
                    submission_id=assigned_submission_id,
                    slug="assigned-production-article",
                    title="Assigned production article",
                    abstract="Private production abstract.",
                    status="production",
                    created_by_id=editor_id,
                ),
                Article(
                    submission_id=unassigned_submission_id,
                    slug="unassigned-production-article",
                    title="Unassigned production article",
                    abstract="Another private production abstract.",
                    status="production",
                    created_by_id=editor_id,
                ),
            ]
        )
        db.commit()

    authenticate(client, "article-choice-editor@example.test", secret=editor_secret)
    response = client.get("/api/v1/admin/production-articles")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Assigned production article"
    assert items[0]["reference"].startswith("NSAJ-")
    assert "abstract" not in items[0]
    assert "final_file_id" not in items[0]

    restricted_client = TestClient(client.app, raise_server_exceptions=False)
    try:
        unauthenticated = restricted_client.get("/api/v1/admin/production-articles")
        assert unauthenticated.status_code == 401
        authenticate(restricted_client, "article-choice-author@example.test")
        forbidden = restricted_client.get("/api/v1/admin/production-articles")
        assert forbidden.status_code == 403
    finally:
        restricted_client.close()


def test_review_workflow_scopes_files_conflicts_and_decisions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(session_factory, "review-author@example.test", "author")
    editor_id, editor_secret = seed_user(
        session_factory, "review-editor@example.test", "editor_in_chief", mfa=True
    )
    submission_id, _ = seed_submission(
        session_factory, author_id, "editorial_screening", editor_id=editor_id
    )
    with session_factory() as db:
        original_reference = db.get(Submission, submission_id).reference
    editor_csrf = authenticate(
        client, "review-editor@example.test", secret=editor_secret
    )

    invite = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/reviewers",
        json={
            "email": "reviewer@example.test",
            "full_name": "Invited Reviewer",
            "affiliation": "Review Institute",
            "expertise": ["science"],
            "languages": ["English"],
            "due_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
            "round_number": 1,
        },
        headers=csrf_header(editor_csrf),
    )
    assert invite.status_code == 201, invite.text
    assignment_id = uuid.UUID(invite.json()["assignment_id"])
    mail_file = next(get_settings().mail_capture_path.resolve().glob("*.json"))
    mail = json.loads(mail_file.read_text(encoding="utf-8"))
    raw_token = mail["link"].split("#token=", maxsplit=1)[1]
    with session_factory() as db:
        invitation = db.scalar(
            select(Invitation).where(Invitation.email == "reviewer@example.test")
        )
        assert invitation is not None
        assert invitation.token_hash == hash_secret(raw_token)

    reviewer = TestClient(client.app, raise_server_exceptions=False)
    preauth_csrf = reviewer.get("/api/v1/auth/csrf").json()["csrf_token"]
    accepted_account = reviewer.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "password": PASSWORD},
        headers=csrf_header(preauth_csrf),
    )
    assert accepted_account.status_code == 200, accepted_account.text
    reviewer_csrf = accepted_account.json()["csrf_token"]

    response = reviewer.post(
        f"/api/v1/reviewer/assignments/{assignment_id}/respond",
        json={
            "accept": True,
            "confidentiality_accepted": True,
            "has_conflict": True,
            "conflict_details": "A potential collaboration must be reviewed.",
        },
        headers=csrf_header(reviewer_csrf),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "conflict_reported"
    assert (
        reviewer.get(f"/api/v1/reviewer/assignments/{assignment_id}").status_code == 403
    )

    case = client.get(f"/api/v1/editorial/submissions/{submission_id}")
    assert case.status_code == 200
    assert case.json()["reviews"][0]["conflict_status"] == "reported"
    resolved = client.post(
        f"/api/v1/editorial/reviews/{assignment_id}/resolve-conflict?clear=true",
        headers=csrf_header(editor_csrf),
    )
    assert resolved.status_code == 200
    manuscript = reviewer.get(f"/api/v1/reviewer/assignments/{assignment_id}")
    assert manuscript.status_code == 200
    assert manuscript.json()["reference"] == original_reference
    assert manuscript.json()["authors"][0]["full_name"] == "Submitting Author"
    assert len(manuscript.json()["files"]) == 1
    file_id = manuscript.json()["files"][0]["id"]
    assert (
        reviewer.get(
            f"/api/v1/reviewer/assignments/{assignment_id}/files/{file_id}"
        ).status_code
        == 200
    )

    report = reviewer.post(
        f"/api/v1/reviewer/assignments/{assignment_id}/report",
        json={
            "recommendation": "major_revision",
            "comments_to_editor": "Confidential recommendation.",
            "comments_to_author": "Please clarify the methods.",
        },
        headers=csrf_header(reviewer_csrf),
    )
    assert report.status_code == 200
    case = client.get(f"/api/v1/editorial/submissions/{submission_id}").json()
    assert case["reviews"][0]["recommendation"] == "major_revision"
    assert case["status"] == "under_review"

    author = TestClient(client.app, raise_server_exceptions=False)
    author_csrf = authenticate(author, "review-author@example.test")
    decision = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/decision",
        json={
            "decision": "revision_requested",
            "author_letter": "Please submit a revised manuscript.",
            "internal_reason": "The editor reviewed the report.",
            "round_number": 1,
        },
        headers=csrf_header(editor_csrf),
    )
    assert decision.status_code == 200, decision.text
    author_view = author.get(f"/api/v1/author/submissions/{submission_id}/editorial")
    assert author_view.status_code == 200
    assert author_view.json()["reference"] == original_reference
    assert (
        author_view.json()["decisions"][0]["letter"]
        == "Please submit a revised manuscript."
    )
    assert "Invited Reviewer" not in author_view.text

    revised = author.post(
        f"/api/v1/author/submissions/{submission_id}/revisions",
        data={"response_note": "Updated methods section."},
        files={"upload": ("revised.pdf", PDF_BYTES, "application/pdf")},
        headers=csrf_header(author_csrf),
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["status"] == "resubmitted"
    with session_factory() as db:
        assert db.get(Submission, submission_id).reference == original_reference
        assert (
            db.scalar(
                select(SubmissionRevision).where(
                    SubmissionRevision.submission_id == submission_id
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(EditorialDecision).where(
                    EditorialDecision.submission_id == submission_id
                )
            ).decision
            == "revision_requested"
        )

    reviewer.close()
    author.close()


def test_site_admin_cannot_open_confidential_editorial_case(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "admin-boundary-author@example.test", "author"
    )
    editor_id, _ = seed_user(
        session_factory, "boundary-editor@example.test", "editor_in_chief", mfa=True
    )
    admin_id, admin_secret = seed_user(
        session_factory, "boundary-admin@example.test", "site_admin", mfa=True
    )
    submission_id, _ = seed_submission(
        session_factory, author_id, "under_review", editor_id=editor_id
    )
    admin = TestClient(client.app, raise_server_exceptions=False)
    authenticate(admin, "boundary-admin@example.test", secret=admin_secret)
    assert (
        admin.get(f"/api/v1/editorial/submissions/{submission_id}").status_code == 403
    )
    assert admin.get("/api/v1/editorial/queue").status_code == 403
    with session_factory() as db:
        assert db.get(User, admin_id) is not None
    admin.close()


def test_deactivating_an_account_revokes_sessions_and_protects_last_admin(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin_id, admin_secret = seed_user(
        session_factory, "deactivate-admin@example.test", "site_admin", mfa=True
    )
    target_id, _ = seed_user(
        session_factory, "deactivate-target@example.test", "author"
    )
    with session_factory() as db:
        seeded_admin = db.scalar(select(User).where(User.email == "site_admin@example.test"))
        assert seeded_admin is not None
        seeded_admin.is_active = False
        db.commit()
    admin = TestClient(client.app, raise_server_exceptions=False)
    admin_csrf = authenticate(
        admin, "deactivate-admin@example.test", secret=admin_secret
    )
    target = TestClient(client.app, raise_server_exceptions=False)
    authenticate(target, "deactivate-target@example.test")
    response = admin.put(
        f"/api/v1/admin/users/{target_id}/active",
        json={"is_active": False},
        headers=csrf_header(admin_csrf),
    )
    assert response.status_code == 200
    assert target.get("/api/v1/auth/me").status_code == 401
    last_admin = admin.put(
        f"/api/v1/admin/users/{admin_id}/active",
        json={"is_active": False},
        headers=csrf_header(admin_csrf),
    )
    assert last_admin.status_code == 409
    admin.close()
    target.close()


def test_issue_publication_is_atomic_and_exposes_only_verified_metadata(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "publication-author@example.test", "author"
    )
    editor_id, editor_secret = seed_user(
        session_factory, "publication-editor@example.test", "editor_in_chief", mfa=True
    )
    submission_id, file_id = seed_submission(
        session_factory, author_id, "accepted", editor_id=editor_id
    )
    with session_factory() as db:
        original_reference = db.get(Submission, submission_id).reference
    editor_csrf = authenticate(
        client, "publication-editor@example.test", secret=editor_secret
    )

    volume = client.post(
        "/api/v1/admin/volumes",
        json={"number": 1, "year": 2026, "title": "Volume 1"},
        headers=csrf_header(editor_csrf),
    )
    assert volume.status_code == 201, volume.text
    issue = client.post(
        "/api/v1/admin/issues",
        json={
            "volume_id": volume.json()["id"],
            "number": "1",
            "title": "Issue 1",
            "description": "",
        },
        headers=csrf_header(editor_csrf),
    )
    assert issue.status_code == 201, issue.text
    article = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/article",
        json={
            "slug": "private-study-2026",
            "title": "Private study",
            "abstract": "Approved abstract.",
            "final_file_id": str(file_id),
            "license": "CC BY 4.0",
            "doi": "10.5555/nsaj.2026.1",
        },
        headers=csrf_header(editor_csrf),
    )
    assert article.status_code == 201, article.text
    article_id = article.json()["id"]
    assert client.get("/api/v1/public/articles/private-study-2026").status_code == 404
    assigned = client.put(
        f"/api/v1/editorial/articles/{article_id}/issue",
        json={"issue_id": issue.json()["id"]},
        headers=csrf_header(editor_csrf),
    )
    assert assigned.status_code == 200
    readiness = client.get(f"/api/v1/editorial/issues/{issue.json()['id']}/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is False
    blocked = client.post(
        f"/api/v1/editorial/issues/{issue.json()['id']}/publish",
        headers=csrf_header(editor_csrf),
    )
    assert blocked.status_code == 409
    with session_factory() as db:
        assert db.get(Issue, uuid.UUID(issue.json()["id"])).status == "draft"
        assert db.get(Article, uuid.UUID(article_id)).status == "production"

    license_result = client.post(
        f"/api/v1/editorial/articles/{article_id}/license/verify",
        json={"evidence_reference": "approved-license-record-1"},
        headers=csrf_header(editor_csrf),
    )
    assert license_result.status_code == 200
    doi_result = client.post(
        f"/api/v1/editorial/articles/{article_id}/doi/verify",
        json={"evidence_reference": "doi-registration-record-1"},
        headers=csrf_header(editor_csrf),
    )
    assert doi_result.status_code == 200
    ready = client.get(f"/api/v1/editorial/issues/{issue.json()['id']}/readiness")
    assert ready.json()["ready"] is True
    published = client.post(
        f"/api/v1/editorial/issues/{issue.json()['id']}/publish",
        headers=csrf_header(editor_csrf),
    )
    assert published.status_code == 200, published.text
    assert published.json()["published_article_ids"] == [article_id]
    public_article = client.get("/api/v1/public/articles/private-study-2026")
    assert public_article.status_code == 200
    assert public_article.json()["manuscript_reference"] == original_reference
    assert public_article.json()["doi"] == "10.5555/nsaj.2026.1"
    assert public_article.json()["license"] == "CC BY 4.0"
    assert (
        client.get("/api/v1/public/articles/private-study-2026/file").status_code == 200
    )
    assert (
        "DO  - 10.5555/nsaj.2026.1"
        in client.get("/api/v1/public/articles/private-study-2026/citation.ris").text
    )

    action = client.post(
        f"/api/v1/editorial/articles/{article_id}/scholarly-actions",
        json={
            "action_type": "retraction",
            "statement": "A formal retraction notice.",
            "publish_public_notice": True,
        },
        headers=csrf_header(editor_csrf),
    )
    assert action.status_code == 201
    assert (
        client.get("/api/v1/public/articles/private-study-2026").json()[
            "publication_notice"
        ]["type"]
        == "retraction"
    )
    assert (
        client.get("/api/v1/public/articles/private-study-2026/file").status_code == 423
    )
    with session_factory() as db:
        assert (
            db.scalar(
                select(ArticleScholarlyAction).where(
                    ArticleScholarlyAction.article_id == uuid.UUID(article_id)
                )
            )
            is not None
        )


def test_reviewer_cannot_use_someone_elses_assignment(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "other-case-author@example.test", "author"
    )
    reviewer_one_id, _ = seed_user(
        session_factory, "reviewer-one@example.test", "reviewer"
    )
    reviewer_two_id, _ = seed_user(
        session_factory, "reviewer-two@example.test", "reviewer"
    )
    submission_id, file_id = seed_submission(session_factory, author_id, "under_review")
    with session_factory() as db:
        profile_one = ReviewerProfile(
            email="reviewer-one@example.test",
            full_name="Reviewer One",
            user_id=reviewer_one_id,
        )
        profile_two = ReviewerProfile(
            email="reviewer-two@example.test",
            full_name="Reviewer Two",
            user_id=reviewer_two_id,
        )
        db.add_all([profile_one, profile_two])
        db.flush()
        assignment = ReviewAssignment(
            submission_id=submission_id,
            reviewer_profile_id=profile_one.id,
            reviewer_user_id=reviewer_one_id,
            manuscript_file_id=file_id,
            invited_by_id=reviewer_one_id,
            status="accepted",
            conflict_status="clear",
            confidentiality_accepted_at=datetime.now(UTC),
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id
    reviewer = TestClient(client.app, raise_server_exceptions=False)
    authenticate(reviewer, "reviewer-two@example.test")
    assert (
        reviewer.get(f"/api/v1/reviewer/assignments/{assignment_id}").status_code == 404
    )
    reviewer.close()


def test_expired_review_assignment_is_closed_and_audited(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "expired-case-author@example.test", "author"
    )
    reviewer_id, _ = seed_user(
        session_factory, "expired-reviewer@example.test", "reviewer"
    )
    submission_id, file_id = seed_submission(
        session_factory, author_id, "reviewer_invitation"
    )
    with session_factory() as db:
        profile = ReviewerProfile(
            email="expired-reviewer@example.test",
            full_name="Expired Reviewer",
            user_id=reviewer_id,
        )
        db.add(profile)
        db.flush()
        assignment = ReviewAssignment(
            submission_id=submission_id,
            reviewer_profile_id=profile.id,
            reviewer_user_id=reviewer_id,
            manuscript_file_id=file_id,
            invited_by_id=reviewer_id,
            status="invited",
            due_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id
    reviewer = TestClient(client.app, raise_server_exceptions=False)
    authenticate(reviewer, "expired-reviewer@example.test")
    listed = reviewer.get("/api/v1/reviewer/assignments")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "expired"
    with session_factory() as db:
        assert db.get(ReviewAssignment, assignment_id).status == "expired"
        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "review.invitation_expired"
                )
            )
            is not None
        )
    reviewer.close()


def test_editor_in_chief_can_assign_only_submitted_cases_to_eligible_editors(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(
        session_factory, "assignment-author@example.test", "author"
    )
    chief_id, chief_secret = seed_user(
        session_factory, "assignment-chief@example.test", "editor_in_chief", mfa=True
    )
    manager_id, _ = seed_user(
        session_factory, "assignment-manager@example.test", "managing_editor"
    )
    admin_id, admin_secret = seed_user(
        session_factory, "assignment-admin@example.test", "site_admin", mfa=True
    )
    submission_id, _ = seed_submission(session_factory, author_id, "submitted")
    with session_factory() as db:
        db.add(
            Submission(
                reference=f"NSAJ-{uuid.uuid4().hex[:8].upper()}",
                submitting_author_id=author_id,
                status="draft",
                title="Private draft",
                abstract="",
                keywords=[],
                manuscript_type=None,
            )
        )
        db.commit()
    chief_csrf = authenticate(
        client, "assignment-chief@example.test", secret=chief_secret
    )

    unassigned = client.get("/api/v1/editorial/unassigned")
    assert unassigned.status_code == 200
    assert [item["id"] for item in unassigned.json()["items"]] == [str(submission_id)]
    eligible = client.get("/api/v1/editorial/editors")
    assert eligible.status_code == 200
    editor_ids = {item["id"] for item in eligible.json()["items"]}
    assert editor_ids == {str(chief_id), str(manager_id)}
    assert str(admin_id) not in editor_ids
    assert client.get("/api/v1/editorial/audit").status_code == 200

    assignment = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/editors",
        json={"editor_id": str(manager_id), "can_make_decisions": True},
        headers=csrf_header(chief_csrf),
    )
    assert assignment.status_code == 200, assignment.text
    assert client.get("/api/v1/editorial/unassigned").json()["items"] == []
    assert any(
        event["event_type"] == "editorial.editor_assigned"
        for event in client.get("/api/v1/editorial/audit").json()["items"]
    )

    manager = TestClient(client.app, raise_server_exceptions=False)
    authenticate(manager, "assignment-manager@example.test")
    assert manager.get("/api/v1/editorial/queue").json()["items"][0]["id"] == str(
        submission_id
    )
    manager.close()

    admin = TestClient(client.app, raise_server_exceptions=False)
    authenticate(admin, "assignment-admin@example.test", secret=admin_secret)
    assert admin.get("/api/v1/editorial/unassigned").status_code == 403
    assert admin.get("/api/v1/editorial/editors").status_code == 403
    assert admin.get("/api/v1/editorial/audit").status_code == 403
    admin.close()
