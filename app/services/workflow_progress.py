"""Read-only editorial summaries derived from existing workflow records."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EditorAssignment,
    ReviewAssignment,
    Submission,
    SubmissionRevision,
    User,
)


class ReviewCounts(TypedDict):
    invited: int
    accepted: int
    completed: int
    conflict_reported: int
    overdue: int


class WorkflowProgress(TypedDict):
    current_round: int
    bucket: str
    waiting_on: (
        Literal["editor_assignment", "editor", "reviewer", "author", "publication"]
        | None
    )
    next_action: str
    due_at: str | None
    review_counts: ReviewCounts


class AssignedEditor(TypedDict):
    id: str
    display_name: str


@dataclass(frozen=True)
class EditorialSummary:
    assigned_editors: list[AssignedEditor]
    assigned_editor_ids: frozenset[uuid.UUID]
    progress: WorkflowProgress


@dataclass(frozen=True)
class ReviewObservation:
    status: str
    due_at: datetime | None
    conflict_status: str = "unanswered"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def current_review_round(db: Session, submission_id: uuid.UUID) -> int:
    """Return the review round that should receive new invitations/decisions.

    SubmissionRevision.round_number records author resubmissions. The initial
    manuscript is review round 1, the first submitted revision feeds review
    round 2, and so on. Keeping this derivation on the server prevents stale
    clients from attaching a reviewer or decision to an earlier round.
    """
    latest_revision_round = db.scalar(
        select(func.max(SubmissionRevision.round_number)).where(
            SubmissionRevision.submission_id == submission_id
        )
    )
    return (latest_revision_round or 0) + 1


def build_progress(
    status: str,
    current_round: int,
    has_editor: bool,
    reviews: Sequence[ReviewObservation],
    *,
    now: datetime | None = None,
) -> WorkflowProgress:
    """Summarize one round without changing expired invitations or workflow state."""
    now = _as_utc(now or datetime.now(UTC))
    counts: ReviewCounts = {
        "invited": 0,
        "accepted": 0,
        "completed": 0,
        "conflict_reported": 0,
        "overdue": 0,
    }
    deadlines: list[datetime] = []
    for review in reviews:
        due_at = _as_utc(review.due_at) if review.due_at else None
        overdue = due_at is not None and due_at <= now
        if review.status in {"invited", "accepted"} and overdue:
            counts["overdue"] += 1
        # Invitation expiry is derived here; only the existing response/list
        # paths persist expiry and its audit event.
        if review.status == "invited" and overdue:
            continue
        if review.status == "conflict_reported" or review.conflict_status == "reported":
            counts["conflict_reported"] += 1
        elif review.status in {"invited", "accepted", "completed"}:
            counts[review.status] += 1
            if review.status in {"invited", "accepted"} and due_at:
                deadlines.append(due_at)

    progress: WorkflowProgress = {
        "current_round": current_round,
        "bucket": "needs_editor",
        "waiting_on": "editor",
        "next_action": "review_case",
        "due_at": min(deadlines).isoformat() if deadlines else None,
        "review_counts": counts,
    }
    if status in {"published", "declined", "withdrawn"}:
        progress.update(bucket="closed", waiting_on=None, next_action="view_outcome")
    elif not has_editor:
        progress.update(
            bucket="needs_assignment",
            waiting_on="editor_assignment",
            next_action="assign_editor",
        )
    elif status == "resubmitted":
        progress.update(bucket="revisions_received", next_action="review_revision")
    elif status == "revision_requested":
        progress.update(
            bucket="awaiting_author", waiting_on="author", next_action="upload_revision"
        )
    elif status in {"accepted", "production", "scheduled"}:
        action = {
            "accepted": "prepare_production",
            "production": "prepare_publication",
            "scheduled": "await_publication",
        }[status]
        progress.update(
            bucket="production", waiting_on="publication", next_action=action
        )
    elif (status == "editorial_screening" and counts["completed"]
          and not counts["invited"] and not counts["accepted"] and not counts["conflict_reported"]):
        progress.update(bucket="reports_available", next_action="consider_reports")
    elif status in {"submitted", "technical_check", "editorial_screening"}:
        progress["next_action"] = {
            "submitted": "start_technical_check",
            "technical_check": "complete_technical_check",
            "editorial_screening": "screen_manuscript",
        }[status]
    elif status in {"reviewer_invitation", "under_review"}:
        if counts["conflict_reported"]:
            progress["next_action"] = "resolve_conflict"
        elif counts["invited"] or counts["accepted"]:
            progress.update(
                bucket="waiting_review",
                waiting_on="reviewer",
                next_action=(
                    "await_review" if counts["accepted"] else "await_review_response"
                ),
            )
        elif counts["completed"]:
            # This is a navigation hint, not a new editorial decision gate or
            # an assertion that a policy-mandated review count has been met.
            progress.update(bucket="reports_available", next_action="consider_reports")
        else:
            progress.update(bucket="needs_reviewer", next_action="invite_reviewer")
    if status not in {"reviewer_invitation", "under_review"}:
        progress["due_at"] = None
    return progress


def load_editorial_summaries(
    db: Session,
    submissions: Sequence[Submission],
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, EditorialSummary]:
    """Load scalar summary data in three queries, independent of case count."""
    if not submissions:
        return {}
    submission_ids = [submission.id for submission in submissions]
    editors: dict[uuid.UUID, list[AssignedEditor]] = defaultdict(list)
    editor_ids: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for submission_id, editor_id, display_name in db.execute(
        select(EditorAssignment.submission_id, User.id, User.display_name)
        .join(User, User.id == EditorAssignment.editor_id)
        .where(
            EditorAssignment.submission_id.in_(submission_ids),
            EditorAssignment.is_active.is_(True),
        )
        .order_by(User.display_name, User.id)
    ):
        editors[submission_id].append(
            {"id": str(editor_id), "display_name": display_name}
        )
        editor_ids[submission_id].add(editor_id)
    rounds = dict(
        db.execute(
            select(
                SubmissionRevision.submission_id,
                func.max(SubmissionRevision.round_number),
            )
            .where(SubmissionRevision.submission_id.in_(submission_ids))
            .group_by(SubmissionRevision.submission_id)
        ).all()
    )
    reviews: dict[uuid.UUID, list[ReviewObservation]] = defaultdict(list)
    for submission_id, round_number, status, conflict_status, due_at in db.execute(
        select(
            ReviewAssignment.submission_id,
            ReviewAssignment.round_number,
            ReviewAssignment.status,
            ReviewAssignment.conflict_status,
            ReviewAssignment.due_at,
        ).where(ReviewAssignment.submission_id.in_(submission_ids))
    ):
        if round_number == rounds.get(submission_id, 0) + 1:
            reviews[submission_id].append(
                ReviewObservation(status, due_at, conflict_status)
            )
    observed_at = now or datetime.now(UTC)
    return {
        submission.id: EditorialSummary(
            assigned_editors=editors[submission.id],
            assigned_editor_ids=frozenset(editor_ids[submission.id]),
            progress=build_progress(
                submission.status,
                rounds.get(submission.id, 0) + 1,
                bool(editor_ids[submission.id]),
                reviews[submission.id],
                now=observed_at,
            ),
        )
        for submission in submissions
    }


def public_progress(status: str, summary: EditorialSummary) -> dict:
    label = status.replace("_", " ").capitalize()
    if status == "submitted" and summary.assigned_editor_ids:
        label = "Editor assigned"
    elif summary.progress["bucket"] == "reports_available":
        label = "Reviews received · Awaiting editor decision"
    detail = None
    if summary.progress["bucket"] == "reports_available":
        detail = "Reviews received. Awaiting the editor’s decision; no author action is required yet."
    elif summary.progress["bucket"] == "waiting_review":
        detail = "Peer review is in progress. The editorial team will communicate its decision here."
    elif summary.progress["bucket"] == "needs_assignment":
        detail = "Your manuscript has been received and is awaiting editor assignment."
    return {"display_status": label, "editor_assigned": bool(summary.assigned_editor_ids), "status_detail": detail}
