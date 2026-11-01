from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, insert, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema
from test_editorial_publication import (
    PDF_BYTES,
    authenticate,
    csrf_header,
    seed_submission,
    seed_user,
)

from app.core.config import get_settings
from app.db.base import Base
from app.models import (
    AuditEvent,
    EditorAssignment,
    EditorialDecision,
    ReviewAssignment,
    ReviewerProfile,
    ReviewReport,
    Role,
    Submission,
    SubmissionFile,
    SubmissionRevision,
    User,
)
from app.services.workflow_progress import (
    ReviewObservation,
    build_progress,
    load_editorial_summaries,
)

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "has_editor", "review_statuses", "bucket", "waiting_on", "action"),
    [
        ("published", False, [], "closed", None, "view_outcome"),
        ("declined", True, [], "closed", None, "view_outcome"),
        ("withdrawn", True, [], "closed", None, "view_outcome"),
        (
            "submitted",
            False,
            [],
            "needs_assignment",
            "editor_assignment",
            "assign_editor",
        ),
        ("resubmitted", True, [], "revisions_received", "editor", "review_revision"),
        (
            "revision_requested",
            True,
            [],
            "awaiting_author",
            "author",
            "upload_revision",
        ),
        ("accepted", True, [], "production", "publication", "prepare_production"),
        ("production", True, [], "production", "publication", "prepare_publication"),
        ("scheduled", True, [], "production", "publication", "await_publication"),
        ("submitted", True, [], "needs_editor", "editor", "start_technical_check"),
        (
            "technical_check",
            True,
            [],
            "needs_editor",
            "editor",
            "complete_technical_check",
        ),
        (
            "editorial_screening",
            True,
            [],
            "needs_editor",
            "editor",
            "screen_manuscript",
        ),
        (
            "under_review",
            True,
            ["conflict_reported"],
            "needs_editor",
            "editor",
            "resolve_conflict",
        ),
        (
            "under_review",
            True,
            ["accepted", "completed"],
            "waiting_review",
            "reviewer",
            "await_review",
        ),
        (
            "reviewer_invitation",
            True,
            ["invited"],
            "waiting_review",
            "reviewer",
            "await_review_response",
        ),
        (
            "under_review",
            True,
            ["completed", "declined"],
            "reports_available",
            "editor",
            "consider_reports",
        ),
        (
            "reviewer_invitation",
            True,
            ["expired", "cancelled", "declined"],
            "needs_reviewer",
            "editor",
            "invite_reviewer",
        ),
    ],
)
def test_progress_describes_existing_states_without_new_policy_gates(
    status: str,
    has_editor: bool,
    review_statuses: list[str],
    bucket: str,
    waiting_on: str | None,
    action: str,
) -> None:
    reviews = [
        ReviewObservation(value, NOW + timedelta(days=1)) for value in review_statuses
    ]
    progress = build_progress(status, 2, has_editor, reviews, now=NOW)
    assert progress["current_round"] == 2
    assert progress["bucket"] == bucket
    assert progress["waiting_on"] == waiting_on
    assert progress["next_action"] == action


def test_expired_invites_are_not_pending_and_review_deadlines_remain_truthful() -> None:
    reviews = [
        ReviewObservation("invited", NOW.replace(tzinfo=None) - timedelta(hours=1)),
        ReviewObservation("accepted", NOW - timedelta(days=1), "clear"),
        ReviewObservation("accepted", NOW + timedelta(days=1), "clear"),
        ReviewObservation("completed", NOW - timedelta(days=3), "clear"),
        ReviewObservation("declined", NOW - timedelta(days=3)),
    ]
    progress = build_progress("under_review", 1, True, reviews, now=NOW)
    assert progress["review_counts"] == {
        "invited": 0,
        "accepted": 2,
        "completed": 1,
        "conflict_reported": 0,
        "overdue": 2,
    }
    assert progress["due_at"] == (NOW - timedelta(days=1)).isoformat()
    assert progress["bucket"] == "waiting_review"
    expired_only = build_progress("reviewer_invitation", 1, True, reviews[:1], now=NOW)
    assert expired_only["bucket"] == "needs_reviewer"
    assert expired_only["due_at"] is None


def add_review(
    db: Session,
    submission_id: uuid.UUID,
    editor_id: uuid.UUID,
    *,
    round_number: int = 1,
    status: str = "completed",
    due_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
) -> ReviewAssignment:
    reviewer_user = db.get(User, user_id) if user_id else None
    profile = ReviewerProfile(
        email=(
            reviewer_user.email
            if reviewer_user
            else f"private-reviewer-{uuid.uuid4().hex}@example.test"
        ),
        full_name="Confidential Reviewer Identity",
        user_id=user_id,
    )
    db.add(profile)
    db.flush()
    assignment = ReviewAssignment(
        submission_id=submission_id,
        reviewer_profile_id=profile.id,
        reviewer_user_id=user_id,
        invited_by_id=editor_id,
        round_number=round_number,
        status=status,
        due_at=due_at,
        conflict_status="clear" if status == "completed" else "unanswered",
    )
    db.add(assignment)
    db.flush()
    if status == "completed":
        db.add(
            ReviewReport(
                review_assignment_id=assignment.id,
                recommendation="accept",
                comments_to_editor="Confidential editor-only report",
                comments_to_author="Author-facing report",
            )
        )
    return assignment


def test_team_worklist_is_metadata_only_and_case_details_stay_assigned(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(session_factory, "summary-author@example.test", "author")
    chief_id, chief_secret = seed_user(
        session_factory, "summary-chief@example.test", "editor_in_chief", mfa=True
    )
    manager_id, _ = seed_user(
        session_factory, "summary-manager@example.test", "managing_editor"
    )
    associate_id, _ = seed_user(
        session_factory, "summary-associate@example.test", "associate_editor"
    )
    submission_id, _ = seed_submission(
        session_factory, author_id, "under_review", editor_id=manager_id
    )
    other_id, _ = seed_submission(
        session_factory,
        author_id,
        "accepted",
        editor_id=associate_id,
        file_name="other.pdf",
    )
    unassigned_id, _ = seed_submission(
        session_factory, author_id, "submitted", file_name="unassigned.pdf"
    )
    draft_id, _ = seed_submission(
        session_factory, author_id, "draft", file_name="draft.pdf"
    )
    with session_factory() as db:
        db.add(
            EditorAssignment(
                submission_id=submission_id,
                editor_id=associate_id,
                assigned_by_id=chief_id,
            )
        )
        add_review(db, submission_id, manager_id)
        db.commit()
    authenticate(client, "summary-chief@example.test", secret=chief_secret)
    response = client.get("/api/v1/editorial/worklist")
    assert response.status_code == 200, response.text
    rows = {item["id"]: item for item in response.json()["items"]}
    assert set(rows) == {str(submission_id), str(other_id), str(unassigned_id)}
    assert str(draft_id) not in rows
    summary = rows[str(submission_id)]
    assert summary["is_assigned_to_me"] is False
    assert {item["id"] for item in summary["assigned_editors"]} == {
        str(manager_id),
        str(associate_id),
    }
    assert summary["progress"]["bucket"] == "reports_available"
    assert rows[str(unassigned_id)]["progress"]["bucket"] == "needs_assignment"
    for private_value in [
        "Confidential Reviewer Identity",
        "Confidential editor-only report",
        "Author-facing report",
        "Confidential abstract",
        "author@example.test",
        "review.pdf",
    ]:
        assert private_value not in response.text
    assert set(summary) == {
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
    assert (
        client.get(f"/api/v1/editorial/submissions/{submission_id}").status_code == 404
    )
    manager = TestClient(client.app, raise_server_exceptions=False)
    authenticate(manager, "summary-manager@example.test")
    own = manager.get("/api/v1/editorial/worklist")
    assert own.status_code == 200
    assert [row["id"] for row in own.json()["items"]] == [str(submission_id)]
    assert own.json()["items"][0]["is_assigned_to_me"] is True
    assert manager.get(f"/api/v1/editorial/submissions/{other_id}").status_code == 404
    manager.close()


def test_worklist_denies_unauthenticated_noneditors_and_mixed_site_admin(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    assert client.get("/api/v1/editorial/worklist").status_code == 401
    for role in ["author", "reviewer", "editor", "site_admin"]:
        _, secret = seed_user(
            session_factory,
            f"denied-{role}@example.test",
            role,
            mfa=role == "site_admin",
        )
        outsider = TestClient(client.app, raise_server_exceptions=False)
        authenticate(outsider, f"denied-{role}@example.test", secret=secret)
        assert outsider.get("/api/v1/editorial/worklist").status_code == 403
        outsider.close()
    mixed_id, secret = seed_user(
        session_factory, "mixed-admin@example.test", "editor_in_chief", mfa=True
    )
    with session_factory() as db:
        admin_role = db.scalar(select(Role).where(Role.name == "site_admin"))
        mixed_user = db.get(User, mixed_id)
        mixed_user.roles.append(admin_role)
        db.commit()
    authenticate(client, "mixed-admin@example.test", secret=secret)
    assert client.get("/api/v1/editorial/worklist").status_code == 403


def test_current_round_excludes_old_reports_and_expiry_is_read_only(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    author_id, _ = seed_user(session_factory, "round-author@example.test", "author")
    editor_id, secret = seed_user(
        session_factory, "round-editor@example.test", "editor_in_chief", mfa=True
    )
    submission_id, file_id = seed_submission(
        session_factory, author_id, "reviewer_invitation", editor_id=editor_id
    )
    reviewer_user, _ = seed_user(
        session_factory, "round-reviewer@example.test", "reviewer"
    )
    with session_factory() as db:
        db.add(
            SubmissionRevision(
                submission_id=submission_id,
                round_number=1,
                author_id=author_id,
                file_id=file_id,
            )
        )
        old_review = add_review(db, submission_id, editor_id)
        current = add_review(
            db,
            submission_id,
            editor_id,
            round_number=2,
            status="invited",
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
        old_profile_id = old_review.reviewer_profile_id
        old_profile = db.get(ReviewerProfile, old_profile_id)
        old_profile.user_id = reviewer_user
        old_profile.email = "round-reviewer@example.test"
        expired_id = current.id
        db.commit()
    authenticate(client, "round-editor@example.test", secret=secret)
    summary = client.get("/api/v1/editorial/worklist").json()["items"][0]
    assert summary["progress"]["current_round"] == 2
    assert summary["progress"]["bucket"] == "needs_reviewer"
    assert summary["progress"]["review_counts"]["completed"] == 0
    case = client.get(f"/api/v1/editorial/submissions/{submission_id}").json()
    assert case["progress"] == summary["progress"]
    assert {item["round_number"] for item in case["reviews"]} == {1, 2}
    assert str(old_profile_id) in {item["id"] for item in case["reviewer_options"]}
    assert "workflow" in case and isinstance(case["workflow"], list)
    assert case["can_record_decision"] is True
    with session_factory() as db:
        assert db.get(ReviewAssignment, expired_id).status == "invited"
        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "review.invitation_expired"
                )
            )
            is None
        )


def test_second_round_reuses_reviewer_with_revision_file_and_delegated_decision(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.editorial.queue_message", lambda *args, **kwargs: None)
    author_id, _ = seed_user(session_factory, "revision-author@example.test", "author")
    editor_id, _ = seed_user(
        session_factory, "revision-editor@example.test", "managing_editor"
    )
    reviewer_id, _ = seed_user(
        session_factory, "revision-reviewer@example.test", "reviewer"
    )
    submission_id, _ = seed_submission(
        session_factory, author_id, "revision_requested", editor_id=editor_id
    )
    with session_factory() as db:
        old_review = add_review(db, submission_id, editor_id, user_id=reviewer_id)
        old_profile_id = old_review.reviewer_profile_id
        db.add(
            EditorialDecision(
                submission_id=submission_id,
                editor_id=editor_id,
                round_number=1,
                decision="revision_requested",
                author_letter="Please revise.",
            )
        )
        db.commit()
    author = TestClient(client.app, raise_server_exceptions=False)
    author_token = authenticate(author, "revision-author@example.test")
    revision = author.post(
        f"/api/v1/author/submissions/{submission_id}/revisions",
        files={"upload": ("revision-two.pdf", PDF_BYTES, "application/pdf")},
        headers=csrf_header(author_token),
    )
    assert revision.status_code == 201, revision.text
    token = authenticate(client, "revision-editor@example.test")
    transitioned = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/transition",
        json={"to_status": "editorial_screening", "reason": "Check revised paper"},
        headers=csrf_header(token),
    )
    assert transitioned.status_code == 200
    case = client.get(f"/api/v1/editorial/submissions/{submission_id}").json()
    assert case["progress"]["current_round"] == 2
    assert case["can_record_decision"] is True
    option = next(
        item for item in case["reviewer_options"] if item["id"] == str(old_profile_id)
    )
    invited = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/reviewers",
        json={
            "email": option["email"],
            "full_name": option["full_name"],
            "round_number": case["progress"]["current_round"],
            "due_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        },
        headers=csrf_header(token),
    )
    assert invited.status_code == 201, invited.text
    with session_factory() as db:
        review = db.get(ReviewAssignment, uuid.UUID(invited.json()["assignment_id"]))
        revised_file = db.scalar(
            select(SubmissionRevision.file_id).where(
                SubmissionRevision.submission_id == submission_id
            )
        )
        assert review.round_number == 2
        assert review.manuscript_file_id == revised_file
    decision = client.post(
        f"/api/v1/editorial/submissions/{submission_id}/decision",
        json={
            "decision": "declined",
            "author_letter": "Revision reviewed.",
            "round_number": 2,
            "close_open_reviews": True,
            "review_closure_reason": "The editor has completed the second-round assessment.",
        },
        headers=csrf_header(token),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "declined"
    with session_factory() as db:
        assignment = db.scalar(
            select(EditorAssignment).where(
                EditorAssignment.submission_id == submission_id
            )
        )
        assignment.can_make_decisions = False
        db.commit()
    assert (
        client.get(f"/api/v1/editorial/submissions/{submission_id}").json()[
            "can_record_decision"
        ]
        is False
    )
    reviewer = TestClient(client.app, raise_server_exceptions=False)
    authenticate(reviewer, "revision-reviewer@example.test")
    listed = reviewer.get("/api/v1/reviewer/assignments")
    assert listed.status_code == 200
    for item in listed.json()["items"]:
        assert set(item) == {
            "id",
            "reference",
            "title",
            "status",
            "due_at",
            "round_number",
        }
    author.close()
    reviewer.close()


@pytest.fixture
def isolated_progress_schema() -> Iterator[Engine]:
    """Own an isolated PostgreSQL schema; never inspect application case records."""
    url = get_settings().sqlalchemy_url
    assert url.get_backend_name() == "postgresql"
    schema = f"test_workflow_progress_{uuid.uuid4().hex}"
    engine = create_engine(url, pool_pre_ping=True)
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    tables = [
        User.__table__,
        Submission.__table__,
        SubmissionFile.__table__,
        SubmissionRevision.__table__,
        EditorAssignment.__table__,
        ReviewerProfile.__table__,
        ReviewAssignment.__table__,
    ]
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        Base.metadata.create_all(scoped_engine, tables=tables)
        yield scoped_engine
    finally:
        # Drop only this fixture's known tables; no CASCADE or application tables.
        Base.metadata.drop_all(scoped_engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(DropSchema(schema))
        engine.dispose()


def test_postgresql_progress_queries_are_batched_and_round_scoped(
    isolated_progress_schema: Engine,
) -> None:
    engine = isolated_progress_schema
    author_id, editor_id, profile_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    submission_ids = [uuid.uuid4() for _ in range(25)]
    with engine.begin() as connection:
        connection.execute(
            insert(User),
            [
                {
                    "id": author_id,
                    "email": "author@example.test",
                    "display_name": "Author",
                    "password_hash": "test-only",
                },
                {
                    "id": editor_id,
                    "email": "editor@example.test",
                    "display_name": "Editor",
                    "password_hash": "test-only",
                },
            ],
        )
        connection.execute(
            insert(Submission),
            [
                {
                    "id": submission_id,
                    "reference": f"TEST-{index:08d}",
                    "submitting_author_id": author_id,
                    "title": "Private test paper",
                    "status": "under_review",
                }
                for index, submission_id in enumerate(submission_ids)
            ],
        )
        connection.execute(
            insert(EditorAssignment),
            [
                {
                    "submission_id": submission_id,
                    "editor_id": editor_id,
                    "assigned_by_id": editor_id,
                }
                for submission_id in submission_ids
            ],
        )
        connection.execute(
            insert(ReviewerProfile),
            {
                "id": profile_id,
                "email": "reviewer@example.test",
                "full_name": "Private Reviewer",
            },
        )
        file_id = uuid.uuid4()
        connection.execute(
            insert(SubmissionFile),
            {
                "id": file_id,
                "submission_id": submission_ids[0],
                "storage_name": "isolated.pdf",
                "original_name": "isolated.pdf",
                "media_type": "application/pdf",
                "size_bytes": 8,
                "sha256": "a" * 64,
                "scan_status": "clean",
            },
        )
        connection.execute(
            insert(SubmissionRevision),
            {
                "submission_id": submission_ids[0],
                "round_number": 1,
                "author_id": author_id,
                "file_id": file_id,
            },
        )
        connection.execute(
            insert(ReviewAssignment),
            [
                {
                    "submission_id": submission_ids[0],
                    "reviewer_profile_id": profile_id,
                    "invited_by_id": editor_id,
                    "round_number": 1,
                    "status": "completed",
                },
                {
                    "submission_id": submission_ids[0],
                    "reviewer_profile_id": profile_id,
                    "invited_by_id": editor_id,
                    "round_number": 2,
                    "status": "accepted",
                },
            ],
        )
    queries: list[str] = []

    def record_query(*args: object) -> None:
        statement = str(args[2])
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    with Session(engine) as db:
        submissions = db.scalars(select(Submission)).all()
        event.listen(engine, "before_cursor_execute", record_query)
        try:
            one = load_editorial_summaries(db, submissions[:1], now=NOW)
            assert len(queries) == 3
            queries.clear()
            many = load_editorial_summaries(db, submissions, now=NOW)
            assert len(queries) == 3
        finally:
            event.remove(engine, "before_cursor_execute", record_query)
        assert len(one) == 1
        assert len(many) == 25
        revised = many[submission_ids[0]].progress
        assert revised["current_round"] == 2
        assert revised["bucket"] == "waiting_review"
        assert revised["review_counts"]["completed"] == 0
        assert revised["review_counts"]["accepted"] == 1
