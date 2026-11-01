from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import editorial
from app.db.base import Base
from app.db.session import get_db
from app.models import (
    EditorAssignment,
    ReviewAssignment,
    ReviewerProfile,
    Role,
    Submission,
    SubmissionFile,
    SubmissionRevision,
    User,
)
from app.services.workflow_progress import (
    ReviewObservation,
    build_progress,
    current_review_round,
    load_editorial_summaries,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def make_role(db: Session, name: str) -> Role:
    role = Role(name=name)
    db.add(role)
    db.flush()
    return role


def make_user(db: Session, email: str, *roles: Role) -> User:
    user = User(
        email=email,
        password_hash="not-used-in-direct-route-tests",
        display_name=email.split("@", 1)[0].replace(".", " ").title(),
        roles=list(roles),
    )
    db.add(user)
    db.flush()
    return user


def make_submission(
    db: Session,
    author: User,
    reference: str,
    *,
    status: str = "submitted",
    title: str | None = None,
) -> Submission:
    submission = Submission(
        submitting_author_id=author.id,
        reference=reference,
        status=status,
        title=title or f"Title {reference}",
        abstract=f"Private abstract for {reference}",
    )
    db.add(submission)
    db.flush()
    return submission


def assign_editor(
    db: Session,
    submission: Submission,
    editor_user: User,
    assigned_by: User,
    *,
    can_make_decisions: bool = False,
) -> EditorAssignment:
    assignment = EditorAssignment(
        submission_id=submission.id,
        editor_id=editor_user.id,
        assigned_by_id=assigned_by.id,
        can_make_decisions=can_make_decisions,
    )
    db.add(assignment)
    db.flush()
    return assignment


def test_build_progress_distinguishes_waiting_conflicts_reports_and_closed() -> None:
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    live_deadline = now + timedelta(days=2)

    waiting = build_progress(
        "under_review",
        1,
        True,
        [ReviewObservation("accepted", live_deadline, "clear")],
        now=now,
    )
    assert waiting["bucket"] == "waiting_review"
    assert waiting["waiting_on"] == "reviewer"
    assert waiting["due_at"] == live_deadline.isoformat()

    conflict = build_progress(
        "under_review",
        1,
        True,
        [ReviewObservation("conflict_reported", live_deadline, "reported")],
        now=now,
    )
    assert conflict["bucket"] == "needs_editor"
    assert conflict["waiting_on"] == "editor"
    assert conflict["next_action"] == "resolve_conflict"
    assert conflict["review_counts"]["conflict_reported"] == 1

    reports = build_progress(
        "under_review",
        1,
        True,
        [ReviewObservation("completed", None, "clear")],
        now=now,
    )
    assert reports["bucket"] == "reports_available"
    assert reports["next_action"] == "consider_reports"

    overdue_invitation = build_progress(
        "reviewer_invitation",
        1,
        True,
        [ReviewObservation("invited", now - timedelta(hours=1), "unanswered")],
        now=now,
    )
    assert overdue_invitation["review_counts"]["overdue"] == 1
    assert overdue_invitation["review_counts"]["invited"] == 0
    assert overdue_invitation["bucket"] == "needs_reviewer"

    for status in ("declined", "withdrawn", "published"):
        closed = build_progress(status, 1, True, [], now=now)
        assert closed["bucket"] == "closed"
        assert closed["waiting_on"] is None


def test_current_round_and_summary_ignore_prior_round_reports(db: Session) -> None:
    author_role = make_role(db, "author")
    chief_role = make_role(db, "editor_in_chief")
    reviewer_role = make_role(db, "reviewer")
    author = make_user(db, "author@example.test", author_role)
    chief = make_user(db, "chief@example.test", chief_role)
    reviewer = make_user(db, "reviewer@example.test", reviewer_role)

    submission = make_submission(db, author, "NSAJ-ROUND", status="under_review")
    assign_editor(db, submission, chief, chief, can_make_decisions=True)
    original_file = SubmissionFile(
        submission_id=submission.id,
        storage_name=f"{uuid.uuid4()}.pdf",
        original_name="original.pdf",
        media_type="application/pdf",
        size_bytes=100,
        sha256="a" * 64,
        scan_status="clean",
    )
    revised_file = SubmissionFile(
        submission_id=submission.id,
        storage_name=f"{uuid.uuid4()}.pdf",
        original_name="revision.pdf",
        media_type="application/pdf",
        size_bytes=110,
        sha256="b" * 64,
        scan_status="clean",
    )
    db.add_all([original_file, revised_file])
    db.flush()
    db.add(
        SubmissionRevision(
            submission_id=submission.id,
            round_number=1,
            author_id=author.id,
            file_id=revised_file.id,
            response_note="Round two revision",
        )
    )
    profile = ReviewerProfile(
        user_id=reviewer.id,
        email=reviewer.email,
        full_name=reviewer.display_name,
        created_by_id=chief.id,
    )
    db.add(profile)
    db.flush()
    db.add_all(
        [
            ReviewAssignment(
                submission_id=submission.id,
                reviewer_profile_id=profile.id,
                reviewer_user_id=reviewer.id,
                manuscript_file_id=original_file.id,
                invited_by_id=chief.id,
                round_number=1,
                status="completed",
                conflict_status="clear",
            ),
            ReviewAssignment(
                submission_id=submission.id,
                reviewer_profile_id=profile.id,
                reviewer_user_id=reviewer.id,
                manuscript_file_id=revised_file.id,
                invited_by_id=chief.id,
                round_number=2,
                status="invited",
                due_at=datetime.now(UTC) + timedelta(days=3),
            ),
        ]
    )
    db.commit()

    assert current_review_round(db, submission.id) == 2
    summary = load_editorial_summaries(db, [submission])[submission.id]
    assert summary.progress["current_round"] == 2
    assert summary.progress["review_counts"]["completed"] == 0
    assert summary.progress["review_counts"]["invited"] == 1
    assert summary.progress["bucket"] == "waiting_review"


def test_worklist_scope_and_summary_privacy(db: Session) -> None:
    author_role = make_role(db, "author")
    reviewer_role = make_role(db, "reviewer")
    chief_role = make_role(db, "editor_in_chief")
    managing_role = make_role(db, "managing_editor")
    associate_role = make_role(db, "associate_editor")
    admin_role = make_role(db, "site_admin")

    author = make_user(db, "author@example.test", author_role)
    reviewer = make_user(db, "reviewer@example.test", reviewer_role)
    chief = make_user(db, "chief@example.test", chief_role)
    managing = make_user(db, "managing@example.test", managing_role)
    associate = make_user(db, "associate@example.test", associate_role)
    unrelated = make_user(db, "unrelated@example.test", associate_role)
    mixed_admin = make_user(db, "mixed@example.test", chief_role, admin_role)

    draft = make_submission(db, author, "NSAJ-DRAFT", status="draft")
    unassigned = make_submission(db, author, "NSAJ-UNASSIGNED")
    assigned = make_submission(db, author, "NSAJ-ASSIGNED", status="under_review")
    closed = make_submission(db, author, "NSAJ-CLOSED", status="declined")
    assign_editor(db, assigned, managing, chief, can_make_decisions=True)
    assign_editor(db, assigned, associate, chief)
    assign_editor(db, closed, managing, chief)
    db.commit()

    chief_items = editorial.editorial_worklist(db, chief)["items"]
    references = {item["reference"] for item in chief_items}
    assert draft.reference not in references
    assert {unassigned.reference, assigned.reference, closed.reference} <= references

    assigned_summary = next(item for item in chief_items if item["id"] == str(assigned.id))
    assert {editor["id"] for editor in assigned_summary["assigned_editors"]} == {
        str(managing.id),
        str(associate.id),
    }
    assert assigned_summary["is_assigned_to_me"] is False
    assert set(assigned_summary) == {
        "id",
        "reference",
        "title",
        "status",
        "status_detail",
        "display_status",
        "editor_assigned",
        "assigned_editors",
        "is_assigned_to_me",
        "progress",
    }
    assert "abstract" not in assigned_summary
    assert "authors" not in assigned_summary
    assert "files" not in assigned_summary
    assert "reviews" not in assigned_summary

    managing_items = editorial.editorial_worklist(db, managing)["items"]
    assert {item["reference"] for item in managing_items} == {
        assigned.reference,
        closed.reference,
    }
    associate_items = editorial.editorial_worklist(db, associate)["items"]
    assert {item["reference"] for item in associate_items} == {assigned.reference}
    assert editorial.editorial_worklist(db, unrelated)["items"] == []

    managing_case = editorial.get_editorial_case(assigned.id, db, managing)
    assert managing_case["can_record_decision"] is True
    assert "progress" in managing_case
    assert "workflow" in managing_case
    associate_case = editorial.get_editorial_case(assigned.id, db, associate)
    assert associate_case["can_record_decision"] is False

    for disallowed in (author, reviewer, mixed_admin):
        with pytest.raises(HTTPException) as exc:
            editorial.editorial_worklist(db, disallowed)
        assert exc.value.status_code == 403

    # Team-summary visibility for the Chief must not become case-detail access.
    with pytest.raises(HTTPException) as exc:
        editorial.get_editorial_case(unassigned.id, db, chief)
    assert exc.value.status_code == 404


def test_worklist_requires_authentication(db: Session) -> None:
    app = FastAPI()
    app.include_router(editorial.router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).get("/api/v1/editorial/worklist")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


def test_second_round_invitation_uses_latest_revision_file(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    author_role = make_role(db, "author")
    managing_role = make_role(db, "managing_editor")
    reviewer_role = make_role(db, "reviewer")
    author = make_user(db, "author@example.test", author_role)
    manager = make_user(db, "manager@example.test", managing_role)
    reviewer = make_user(db, "reviewer@example.test", reviewer_role)
    submission = make_submission(db, author, "NSAJ-R2-INVITE", status="editorial_screening")
    assign_editor(db, submission, manager, manager)

    original_file = SubmissionFile(
        submission_id=submission.id,
        storage_name=f"{uuid.uuid4()}.pdf",
        original_name="original.pdf",
        media_type="application/pdf",
        size_bytes=100,
        sha256="c" * 64,
        scan_status="clean",
    )
    revision_file = SubmissionFile(
        submission_id=submission.id,
        storage_name=f"{uuid.uuid4()}.pdf",
        original_name="round-2.pdf",
        media_type="application/pdf",
        size_bytes=110,
        sha256="d" * 64,
        scan_status="clean",
    )
    db.add_all([original_file, revision_file])
    db.flush()
    db.add(
        SubmissionRevision(
            submission_id=submission.id,
            round_number=1,
            author_id=author.id,
            file_id=revision_file.id,
            response_note="Revised manuscript",
        )
    )
    profile = ReviewerProfile(
        user_id=reviewer.id,
        email=reviewer.email,
        full_name=reviewer.display_name,
        created_by_id=manager.id,
    )
    db.add(profile)
    db.commit()

    monkeypatch.setattr(
        editorial,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="development",
            public_base_url="http://localhost:3000",
            token_expiry_hours=24,
        ),
    )
    monkeypatch.setattr(editorial, "queue_message", lambda *args, **kwargs: None)

    stale_payload = editorial.ReviewerInviteInput(
        email=reviewer.email,
        full_name=reviewer.display_name,
        due_at=datetime.now(UTC) + timedelta(days=5),
        round_number=1,
    )
    with pytest.raises(HTTPException) as exc:
        editorial.invite_reviewer(submission.id, stale_payload, db, manager)
    assert exc.value.status_code == 409
    assert "round changed" in str(exc.value.detail).lower()

    payload = stale_payload.model_copy(update={"round_number": 2})
    result = editorial.invite_reviewer(submission.id, payload, db, manager)
    assignment = db.scalar(
        select(ReviewAssignment).where(
            ReviewAssignment.id == uuid.UUID(result["assignment_id"])
        )
    )
    assert assignment is not None
    assert assignment.round_number == 2
    assert assignment.manuscript_file_id == revision_file.id


def test_second_round_decision_requires_current_round_and_delegation(db: Session) -> None:
    author_role = make_role(db, "author")
    managing_role = make_role(db, "managing_editor")
    author = make_user(db, "author@example.test", author_role)
    manager = make_user(db, "manager@example.test", managing_role)
    submission = make_submission(db, author, "NSAJ-R2-DECISION", status="under_review")
    assignment = assign_editor(db, submission, manager, manager, can_make_decisions=False)
    db.add(
        SubmissionRevision(
            submission_id=submission.id,
            round_number=1,
            author_id=author.id,
            file_id=uuid.uuid4(),
            response_note="Revision",
        )
    )
    db.commit()

    payload = editorial.DecisionInput(
        decision="accepted",
        author_letter="Accepted after revision.",
        round_number=2,
    )
    with pytest.raises(HTTPException) as exc:
        editorial.make_editorial_decision(submission.id, payload, db, manager)
    assert exc.value.status_code == 403

    assignment.can_make_decisions = True
    db.commit()
    stale = payload.model_copy(update={"round_number": 1})
    with pytest.raises(HTTPException) as exc:
        editorial.make_editorial_decision(submission.id, stale, db, manager)
    assert exc.value.status_code == 409
    assert "round changed" in str(exc.value.detail).lower()

    result = editorial.make_editorial_decision(submission.id, payload, db, manager)
    assert result["status"] == "accepted"
    assert current_review_round(db, submission.id) == 2
